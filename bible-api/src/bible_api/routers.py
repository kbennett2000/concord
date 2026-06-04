"""The ``/v1`` read endpoints: ``/verses/{ref}`` and ``/chapters/{book}/{chapter}``.

Both resolve books via :class:`~bible_core.resolver.SqliteBookResolver`, query the corpus,
raise :class:`~.errors.NoVersesFoundError` when nothing matches, and shape the result via
the shared shaper into whichever ``?format=`` was requested.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, Literal

from bible_core.parser import UnknownBookError, parse_reference
from bible_core.queries import QueryResult, get_chapter, get_verses, search_verses
from bible_core.resolver import SqliteBookResolver
from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from .caching import cached_json_response
from .dependencies import get_conn, resolve_translation, resolve_translations
from .errors import BookFilterError, NoVersesFoundError
from .schemas import SearchHit, SearchResponse
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
