"""The ``/v1`` read endpoints: ``/verses/{ref}`` and ``/chapters/{book}/{chapter}``.

Both resolve books via :class:`~bible_core.resolver.SqliteBookResolver`, query the corpus,
raise :class:`~.errors.NoVersesFoundError` when nothing matches, and shape the result via
the shared shaper into whichever ``?format=`` was requested.
"""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Annotated, Any, Literal

import structlog
from bible_core.parser import UnknownBookError, parse_reference
from bible_core.queries import (
    CrossRefRow,
    NoteCrossRefRow,
    NoteRow,
    PlaceRow,
    QueryResult,
    SectionHeadingRow,
    count_place_verses,
    distinct_place_types,
    get_books,
    get_chapter,
    get_cross_references,
    get_notes,
    get_place,
    get_place_verses,
    get_places_for_reference,
    get_random_verse,
    get_section_headings,
    get_translations,
    get_verse_text,
    get_verses,
    list_places,
    reference_exists,
    search_notes,
    search_verses,
    search_verses_multi,
)
from bible_core.resolver import SqliteBookResolver
from bible_semantic.model import embed_query
from bible_semantic.search import cosine_top_k
from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from .caching import cached_json_response, no_store_json_response
from .dependencies import (
    get_conn,
    resolve_display_translation,
    resolve_translation,
    resolve_translations,
)
from .errors import (
    BookFilterError,
    FilterError,
    NoMatchError,
    NoVersesFoundError,
    SemanticBusyError,
    SemanticTimeoutError,
    SemanticUnavailableError,
    UnknownPlaceError,
    UnknownTranslationError,
)
from .schemas import (
    Book,
    BooksResponse,
    CrossRefEntry,
    CrossRefResponse,
    CrossRefSource,
    CrossRefTarget,
    HeadingsResponse,
    NoteCrossReference,
    NoteSearchHit,
    NoteSearchResponse,
    NotesResponse,
    PlaceDetail,
    PlacesResponse,
    PlaceSummary,
    PlaceVerse,
    PlaceVersesResponse,
    RandomResponse,
    RandomVerse,
    SearchHit,
    SearchResponse,
    SectionHeading,
    SemanticSearchHit,
    SemanticSearchResponse,
    Translation,
    TranslationsResponse,
    TranslatorNote,
    VersePlacesResponse,
)
from .shaping import shape_grouped, shape_parallel

router = APIRouter(prefix="/v1")

Format = Literal["parallel", "grouped"]

# Defense-in-depth input bounds. A reference or search query above these lengths is abusive,
# not legitimate use (the longest real reference is a few dozen chars; FTS5/semantic queries
# are short phrases) — reject at the HTTP edge before parsing or fanning out to the DB/model.
# The parser also caps verse-list elements independently (bible_core), since it's embeddable
# outside this web layer.
MAX_REF_LENGTH = 256
MAX_QUERY_LENGTH = 1000


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
    ref: Annotated[str, Path(max_length=MAX_REF_LENGTH)],
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
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)],
    translation: str | None = None,
    translations: str | None = None,
    book: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    book_id: str | None = None
    if book is not None and book.strip():
        info = SqliteBookResolver(conn).resolve(book)
        if info is None:
            raise BookFilterError(f"unknown book filter {book!r}")
        book_id = info.id

    # ?translations= (plural) opts into multi-translation mode (v5-S2, ADR-0003); absent/blank keeps
    # the byte-for-byte single-translation path. ?translation= (singular) still selects the one.
    if translations is None or not translations.strip():
        translation_id = resolve_translation(request, translation)
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

    if translations.strip() == "*":
        ids: tuple[str, ...] = tuple(sorted(request.app.state.translations))
    else:
        ids = resolve_translations(request, translations)

    multi = search_verses_multi(conn, q, ids, book_id, limit, offset)
    response = SearchResponse(
        query=q,
        translation=ids[0],  # the primary (first resolved); matches[0] is the top-ranked snippet
        translations=list(ids),
        book=book_id,
        limit=limit,
        offset=offset,
        total=multi.total,
        hits=[
            SearchHit(
                book=hit.book_id,
                chapter=hit.chapter,
                verse=hit.verse,
                reference=f"{hit.book_name} {hit.chapter}:{hit.verse}",
                snippet=hit.matches[0].snippet,
                matches={m.translation_id: m.snippet for m in hit.matches},
            )
            for hit in multi.hits
        ],
    )
    return cached_json_response(response, request)


# The closed set of note types (mirrors the ``note_type`` CHECK constraint in bible_core.schema).
# A fixed enum, so an unknown ``?type=`` is a 400 filter error (like ``/places`` status).
NOTE_TYPES = ("tn", "sn", "tc", "map", "other")


@router.get("/notes/search")
def notes_search_endpoint(
    request: Request,
    conn: Conn,
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)],
    translation: str | None = None,
    type: str | None = None,
    book: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    # All three filters are optional (omit ⇒ search every loaded translation/type/book).
    # translation is a *filter* here, not the defaulted single selector of /search, so we
    # validate-without-defaulting: unknown id → 404 (consistent with every translation param);
    # unknown type → 400 (closed enum); unknown book → 400 (same as /search). An instance with
    # no notes simply matches nothing → 200 empty, never an error.
    translation_filter: str | None = None
    if translation is not None and translation.strip():
        tid = translation.strip().upper()
        loaded: set[str] = request.app.state.translations
        if tid not in loaded:
            raise UnknownTranslationError(tid, list(loaded))
        translation_filter = tid

    type_filter: str | None = None
    if type is not None and type.strip():
        type_filter = type.strip()
        if type_filter not in NOTE_TYPES:
            raise FilterError(
                "unknown_type",
                f"unknown note type {type_filter!r}",
                {"type": type_filter, "available": list(NOTE_TYPES)},
            )

    book_id: str | None = None
    if book is not None and book.strip():
        info = SqliteBookResolver(conn).resolve(book)
        if info is None:
            raise BookFilterError(f"unknown book filter {book!r}")
        book_id = info.id

    page = search_notes(conn, q, translation_filter, type_filter, book_id, limit, offset)
    response = NoteSearchResponse(
        query=q,
        translation=translation_filter,
        type=type_filter,
        book=book_id,
        limit=limit,
        offset=offset,
        total=page.total,
        hits=[
            NoteSearchHit(
                book=hit.book_id,
                chapter=hit.chapter,
                verse=hit.verse,
                reference=f"{hit.book_name} {hit.chapter}:{hit.verse}",
                translation=hit.translation_id,
                type=hit.note_type,
                char_offset=hit.char_offset,
                marker=hit.marker,
                ordinal=hit.ordinal,
                snippet=hit.snippet,
            )
            for hit in page.hits
        ],
    )
    return cached_json_response(response, request)


def _run_inference(
    semaphore: threading.Semaphore, store: Any, q: str, limit: int, min_score: float | None
) -> list[Any]:
    """Run the ONNX inference + cosine top-k, releasing the concurrency permit when done.

    The permit is released *here* — never in the handler — so a request whose caller has
    already given up on the wall-clock deadline (ADR-0002) keeps holding its slot until the
    inference truly finishes. That keeps the concurrency cap coupled to real CPU exactly as
    ADR-0001 requires: a retry after a timeout hits a full cap and is shed with 503, instead
    of stacking a second slow pass on top of the first. The semaphore is the single owner —
    released exactly once, on every path (success, error, or post-timeout completion).
    """
    try:
        return cosine_top_k(embed_query(q), store.matrix, store.refs, limit, min_score)
    finally:
        semaphore.release()


@router.get("/semantic-search")
def semantic_search_endpoint(
    request: Request,
    conn: Conn,
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)],
    translation: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    min_score: Annotated[float | None, Query(ge=-1.0, le=1.0)] = None,
    include_text: bool = True,
) -> Response:
    # Validate the display translation first (404 on unknown) — before the store check, so
    # an unknown translation is a 404 even when semantic search is disabled.
    display_translation = resolve_display_translation(request, translation)

    store = request.app.state.semantic_store
    if store is None:
        raise SemanticUnavailableError("semantic search is not enabled on this server")

    # Search always runs in WEB space; `translation` only controls the displayed text.
    # Concurrency cap (ADR-0001): bound simultaneous ONNX inferences so a tight loop / retry
    # storm can't saturate CPU on a shared box. Non-blocking — shed the excess with 503 +
    # Retry-After rather than queueing. Wraps only the inference; text hydration stays outside.
    sem = request.app.state.semantic_semaphore
    if sem is None:
        # No cap: run inline. A deadline has no permit to couple to here, so it doesn't apply
        # (an uncapped box already opts out of this protection; ADR-0002).
        matches = cosine_top_k(embed_query(q), store.matrix, store.refs, limit, min_score)
    elif not sem.acquire(blocking=False):
        structlog.get_logger("bible_api").warning(
            "concord.api.semantic_shed", limit=request.app.state.semantic_max_concurrency
        )
        raise SemanticBusyError("semantic search is at capacity; retry shortly")
    else:
        # Permit held; ownership passes to the worker, which releases it exactly once.
        executor = request.app.state.semantic_executor
        if executor is None:
            # Deadline disabled (timeout 0): run synchronously — ADR-0001 behaviour, unchanged.
            matches = _run_inference(sem, store, q, limit, min_score)
        else:
            timeout_s = request.app.state.semantic_timeout_s
            future = executor.submit(_run_inference, sem, store, q, limit, min_score)
            try:
                matches = future.result(timeout=timeout_s)
            except FuturesTimeoutError:
                # Caller gives up, but the worker keeps running and holds its permit until done,
                # so the cap stays coupled to CPU and a retry hits semantic_busy (ADR-0002).
                structlog.get_logger("bible_api").warning(
                    "concord.api.semantic_timeout", timeout_s=timeout_s
                )
                raise SemanticTimeoutError(
                    "semantic search exceeded its time budget; retry shortly"
                ) from None
    book_names: dict[str, str] = request.app.state.book_names
    results = [
        SemanticSearchHit(
            book=ref.book_id,
            chapter=ref.chapter,
            verse=ref.verse,
            reference=f"{book_names.get(ref.book_id, ref.book_id)} {ref.chapter}:{ref.verse}",
            score=round(score, 4),
            text=(
                get_verse_text(conn, display_translation, ref.book_id, ref.chapter, ref.verse)
                if include_text
                else None
            ),
        )
        for ref, score in matches
    ]
    response = SemanticSearchResponse(
        query=q, translation=display_translation, count=len(results), results=results
    )
    return cached_json_response(response, request)


def _target_reference(row: CrossRefRow) -> str:
    if row.to_verse_end is not None and row.to_verse_end != row.to_verse_start:
        return f"{row.to_book_name} {row.to_chapter}:{row.to_verse_start}-{row.to_verse_end}"
    return f"{row.to_book_name} {row.to_chapter}:{row.to_verse_start}"


@router.get("/cross-references/{ref}")
def cross_references_endpoint(
    ref: Annotated[str, Path(max_length=MAX_REF_LENGTH)],
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


# --- translator's notes (v4): passage read --------------------------------------------


def _note_xref_reference(x: NoteCrossRefRow) -> str:
    """Human reference for a note's cross-ref target (book name + chapter:start[-end])."""
    if x.to_verse_end is not None and x.to_verse_end != x.to_verse_start:
        return f"{x.to_book_name} {x.to_chapter}:{x.to_verse_start}-{x.to_verse_end}"
    return f"{x.to_book_name} {x.to_chapter}:{x.to_verse_start}"


def _translator_note(row: NoteRow) -> TranslatorNote:
    return TranslatorNote(
        book=row.book_id,
        chapter=row.chapter,
        verse=row.verse,
        reference=f"{row.book_name} {row.chapter}:{row.verse}",
        type=row.note_type,
        text=row.text,
        char_offset=row.char_offset,
        marker=row.marker,
        ordinal=row.ordinal,
        cross_references=[
            NoteCrossReference(
                to_book=x.to_book_id,
                to_chapter=x.to_chapter,
                to_verse_start=x.to_verse_start,
                to_verse_end=x.to_verse_end,
                reference=_note_xref_reference(x),
            )
            for x in row.cross_references
        ],
    )


@router.get("/translations/{translation}/notes/{book}/{chapter}")
def notes_endpoint(
    translation: str,
    book: str,
    request: Request,
    conn: Conn,
    chapter: Annotated[int, Path(ge=1)],
    verse: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    # Unknown translation → 404; unknown book → 404 (matches the chapter read). A KNOWN
    # translation with no notes (the public image, or any translation but a user's NET) returns
    # 200 with an empty list — not an error (SPEC v4 §5). An empty/out-of-range chapter or verse
    # likewise returns empty, since notes are an overlay (no verse-range validation here).
    translation_id = resolve_translation(request, translation)
    info = SqliteBookResolver(conn).resolve(book)
    if info is None:
        raise UnknownBookError(f"unrecognised book {book!r}")

    rows = get_notes(conn, translation_id, info.id, chapter, verse)
    response = NotesResponse(
        translation=translation_id,
        book=info.id,
        chapter=chapter,
        verse=verse,
        total=len(rows),
        notes=[_translator_note(row) for row in rows],
    )
    return cached_json_response(response, request)


def _section_heading(row: SectionHeadingRow) -> SectionHeading:
    return SectionHeading(
        book=row.book_id,
        chapter=row.chapter,
        before_verse=row.before_verse,
        text=row.text,
        ordinal=row.ordinal,
        reference=f"{row.book_name} {row.chapter}:{row.before_verse}",
    )


@router.get("/translations/{translation}/headings/{book}/{chapter}")
def headings_endpoint(
    translation: str,
    book: str,
    request: Request,
    conn: Conn,
    chapter: Annotated[int, Path(ge=1)],
) -> Response:
    # Mirrors the notes read: unknown translation → 404; unknown book → 404. A KNOWN translation
    # with no headings for the chapter (e.g. BSB, which ships none) returns 200 with an empty
    # list — not an error. Headings are an overlay, so an out-of-range chapter likewise returns
    # empty (no chapter-range validation here).
    translation_id = resolve_translation(request, translation)
    info = SqliteBookResolver(conn).resolve(book)
    if info is None:
        raise UnknownBookError(f"unrecognised book {book!r}")

    rows = get_section_headings(conn, translation_id, info.id, chapter)
    response = HeadingsResponse(
        translation=translation_id,
        book=info.id,
        chapter=chapter,
        total=len(rows),
        headings=[_section_heading(row) for row in rows],
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


# --- geography (v3): places + the bi-directional place↔verse link ---------------------

# The fixed status enum (mirrors the places.status CHECK in the schema).
PLACE_STATUSES = ("identified", "disputed", "unknown", "symbolic", "multiple")


def _place_summary(place: PlaceRow) -> PlaceSummary:
    """Project a PlaceRow to the summary shape (coords surfaced as named lat/lon)."""
    return PlaceSummary(
        id=place.id,
        friendly_id=place.friendly_id,
        name=place.name,
        type=place.type,
        latitude=place.latitude,
        longitude=place.longitude,
        confidence=place.confidence,
        confidence_score=place.confidence_score,
        status=place.status,
    )


@router.get("/places")
def places_endpoint(
    request: Request,
    conn: Conn,
    type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    type_filter = type.strip() if type and type.strip() else None
    if type_filter is not None:
        available = distinct_place_types(conn)
        if type_filter not in available:
            raise FilterError(
                "unknown_type",
                f"unknown place type {type_filter!r}",
                {"type": type_filter, "available": available},
            )

    status_filter = status.strip() if status and status.strip() else None
    if status_filter is not None and status_filter not in PLACE_STATUSES:
        raise FilterError(
            "unknown_status",
            f"unknown place status {status_filter!r}",
            {"status": status_filter, "available": list(PLACE_STATUSES)},
        )

    q_filter = q.strip() if q and q.strip() else None
    page = list_places(conn, type_filter, status_filter, q_filter, limit, offset)
    response = PlacesResponse(
        type=type_filter,
        status=status_filter,
        q=q_filter,
        limit=limit,
        offset=offset,
        total=page.total,
        places=[_place_summary(p) for p in page.rows],
    )
    return cached_json_response(response, request)


@router.get("/places/{place_id}")
def place_detail_endpoint(place_id: str, request: Request, conn: Conn) -> Response:
    place = get_place(conn, place_id)
    if place is None:
        raise UnknownPlaceError(place_id)
    response = PlaceDetail(
        id=place.id,
        friendly_id=place.friendly_id,
        name=place.name,
        url_slug=place.url_slug,
        type=place.type,
        preceding_article=place.preceding_article,
        latitude=place.latitude,
        longitude=place.longitude,
        confidence=place.confidence,
        confidence_score=place.confidence_score,
        status=place.status,
        modern_name=place.modern_name,
        verse_count=count_place_verses(conn, place.id),
    )
    return cached_json_response(response, request)


@router.get("/places/{place_id}/verses")
def place_verses_endpoint(
    place_id: str,
    request: Request,
    conn: Conn,
    translation: str | None = None,
    include_text: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    if get_place(conn, place_id) is None:
        raise UnknownPlaceError(place_id)

    translation_id = resolve_translation(request, translation) if include_text else None
    rows, total = get_place_verses(conn, place_id, limit, offset)
    verses = [
        PlaceVerse(
            book=row.book_id,
            chapter=row.chapter,
            verse=row.verse,
            reference=f"{row.book_name} {row.chapter}:{row.verse}",
            text=(
                get_verse_text(conn, translation_id, row.book_id, row.chapter, row.verse)
                if translation_id is not None
                else None
            ),
        )
        for row in rows
    ]
    response = PlaceVersesResponse(
        id=place_id,
        translation=translation_id,
        include_text=include_text,
        limit=limit,
        offset=offset,
        total=total,
        verses=verses,
    )
    return cached_json_response(response, request)


@router.get("/verses/{ref}/places")
def verse_places_endpoint(
    ref: Annotated[str, Path(max_length=MAX_REF_LENGTH)], request: Request, conn: Conn
) -> Response:
    # parse_reference raises ParseError (400) / UnknownBookError (404), already wired. A valid
    # ref naming no place returns 200 with an empty list (SPEC v3 §7).
    reference = parse_reference(ref, SqliteBookResolver(conn))
    page = get_places_for_reference(conn, reference)
    response = VersePlacesResponse(
        reference=reference.echo,
        total=page.total,
        places=[_place_summary(p) for p in page.rows],
    )
    return cached_json_response(response, request)
