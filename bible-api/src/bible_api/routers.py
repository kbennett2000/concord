"""The ``/v1`` read endpoints: ``/verses/{ref}`` and ``/chapters/{book}/{chapter}``.

Both resolve books via :class:`~bible_core.resolver.SqliteBookResolver`, query the corpus,
raise :class:`~.errors.NoVersesFoundError` when nothing matches, and shape the result via
the shared shaper into whichever ``?format=`` was requested.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, Literal

from bible_core.parser import UnknownBookError, parse_reference
from bible_core.queries import (
    CrossRefRow,
    QueryResult,
    get_books,
    get_chapter,
    get_cross_references,
    get_random_verse,
    get_translations,
    get_verse_text,
    get_verses,
    reference_exists,
    search_verses,
)
from bible_core.resolver import SqliteBookResolver
from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from .caching import cached_json_response, no_store_json_response
from .dependencies import get_conn, resolve_translation, resolve_translations
from .errors import BookFilterError, NoMatchError, NoVersesFoundError
from .schemas import (
    Book,
    BooksResponse,
    CrossRefEntry,
    CrossRefResponse,
    CrossRefSource,
    CrossRefTarget,
    RandomResponse,
    RandomVerse,
    SearchHit,
    SearchResponse,
    Translation,
    TranslationsResponse,
)
from .shaping import shape_grouped, shape_parallel

router = APIRouter(prefix="/v1")

Format = Literal["parallel", "grouped"]


def _respond(result: QueryResult, fmt: Format, request: Request) -> Response:
    if not result.rows:
        raise NoVersesFoundError(
            f"no verses found for {result.reference!r} in the requested translations"
        )
    model = shape_grouped(result) if fmt == "grouped" else shape_parallel(result)
    return cached_json_response(model, request)


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


@router.get("/verses/{ref}")
def get_verses_endpoint(
    ref: str,
    request: Request,
    conn: Conn,
    translations: str | None = None,
    format: Format = "parallel",
) -> Response:
    ids = resolve_translations(request, translations)
    reference = parse_reference(ref, SqliteBookResolver(conn))
    return _respond(get_verses(conn, reference, ids), format, request)


@router.get("/chapters/{book}/{chapter}")
def get_chapter_endpoint(
    book: str,
    request: Request,
    conn: Conn,
    chapter: Annotated[int, Path(ge=1)],
    translations: str | None = None,
    format: Format = "parallel",
) -> Response:
    ids = resolve_translations(request, translations)
    info = SqliteBookResolver(conn).resolve(book)
    if info is None:
        raise UnknownBookError(f"unrecognised book {book!r}")
    return _respond(get_chapter(conn, info.id, info.name, chapter, ids), format, request)


@router.get("/search")
def search_endpoint(
    request: Request,
    conn: Conn,
    q: Annotated[str, Query(min_length=1)],
    translation: str | None = None,
    book: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    translation_id = resolve_translation(request, translation)

    book_id: str | None = None
    if book is not None and book.strip():
        info = SqliteBookResolver(conn).resolve(book)
        if info is None:
            raise BookFilterError(f"unknown book filter {book!r}")
        book_id = info.id

    page = search_verses(conn, q, translation_id, book_id, limit, offset)
    response = SearchResponse(
        query=q,
        translation=translation_id,
        book=book_id,
        limit=limit,
        offset=offset,
        total=page.total,
        hits=[
            SearchHit(
                book=hit.book_id,
                chapter=hit.chapter,
                verse=hit.verse,
                reference=f"{hit.book_name} {hit.chapter}:{hit.verse}",
                snippet=hit.snippet,
            )
            for hit in page.hits
        ],
    )
    return cached_json_response(response, request)


def _target_reference(row: CrossRefRow) -> str:
    if row.to_verse_end is not None and row.to_verse_end != row.to_verse_start:
        return f"{row.to_book_name} {row.to_chapter}:{row.to_verse_start}-{row.to_verse_end}"
    return f"{row.to_book_name} {row.to_chapter}:{row.to_verse_start}"


@router.get("/cross-references/{ref}")
def cross_references_endpoint(
    ref: str,
    request: Request,
    conn: Conn,
    include_text: bool = False,
    translation: str | None = None,
    min_votes: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    reference = parse_reference(ref, SqliteBookResolver(conn))
    if not reference_exists(conn, reference):
        raise NoVersesFoundError(f"{reference.echo!r} is out of range in every loaded translation")

    translation_id = resolve_translation(request, translation) if include_text else None
    page = get_cross_references(conn, reference, min_votes, limit, offset)

    entries: list[CrossRefEntry] = []
    for row in page.rows:
        text = (
            get_verse_text(conn, translation_id, row.to_book_id, row.to_chapter, row.to_verse_start)
            if translation_id is not None
            else None
        )
        entries.append(
            CrossRefEntry(
                from_=CrossRefSource(
                    book=row.from_book_id,
                    chapter=row.from_chapter,
                    verse=row.from_verse,
                    reference=f"{row.from_book_name} {row.from_chapter}:{row.from_verse}",
                ),
                to=CrossRefTarget(
                    book=row.to_book_id,
                    chapter=row.to_chapter,
                    verse_start=row.to_verse_start,
                    verse_end=row.to_verse_end,
                    reference=_target_reference(row),
                ),
                votes=row.votes,
                text=text,
            )
        )

    response = CrossRefResponse(
        reference=reference.echo,
        translation=translation_id,
        min_votes=min_votes,
        limit=limit,
        offset=offset,
        total=page.total,
        cross_references=entries,
    )
    return cached_json_response(response, request)


@router.get("/books")
def books_endpoint(request: Request, conn: Conn) -> Response:
    books = [
        Book(
            id=b.id,
            name=b.name,
            testament=b.testament,
            chapter_count=b.chapter_count,
            canonical_order=b.canonical_order,
        )
        for b in get_books(conn)
    ]
    return cached_json_response(BooksResponse(books=books), request)


@router.get("/translations")
def translations_endpoint(request: Request, conn: Conn) -> Response:
    translations = [
        Translation(
            id=t.id,
            name=t.name,
            language=t.language,
            versification=t.versification,
            attribution=t.attribution,
        )
        for t in get_translations(conn)
    ]
    return cached_json_response(TranslationsResponse(translations=translations), request)


@router.get("/random")
def random_endpoint(
    request: Request,
    conn: Conn,
    translation: str | None = None,
    book: str | None = None,
    testament: Annotated[str | None, Query(pattern="(?i)^(ot|nt)$")] = None,
) -> Response:
    translation_id = resolve_translation(request, translation)

    book_id: str | None = None
    if book is not None and book.strip():
        info = SqliteBookResolver(conn).resolve(book)
        if info is None:
            raise BookFilterError(f"unknown book filter {book!r}")
        book_id = info.id

    testament_id = testament.upper() if testament else None

    chosen = get_random_verse(conn, translation_id, book_id, testament_id)
    if chosen is None:
        raise NoMatchError("no verse matches the requested filters")

    response = RandomResponse(
        translation=translation_id,
        book=book_id,
        testament=testament_id,
        verse=RandomVerse(
            book=chosen.book_id,
            chapter=chosen.chapter,
            verse=chosen.verse,
            reference=f"{chosen.book_name} {chosen.chapter}:{chosen.verse}",
            text=chosen.text,
        ),
    )
    # /random must NOT use the immutable-ETag cache — a fresh verse every call.
    return no_store_json_response(response)
