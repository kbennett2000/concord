"""Verse/chapter queries over the loaded corpus.

Pure data access: takes a SQLite connection + structured input and returns flat
``VerseRow`` records the API's shaper turns into parallel or grouped JSON. No web or
Pydantic imports — ``bible-core`` stays standalone (SPEC §2).

Each :class:`~bible_core.parser.Span` maps to **one** SQL query; ranges are expressed as
``BETWEEN`` / linear ``(chapter, verse)`` predicates and never materialized in Python, so
``John 1:1-99999999`` stays one cheap query (the invariant inherited from Slice 3).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .parser import Reference, Span


@dataclass(frozen=True)
class VerseRow:
    """One verse of one translation."""

    book_id: str
    chapter: int
    verse: int
    translation_id: str
    text: str


@dataclass(frozen=True)
class QueryResult:
    """A query's flat rows plus the metadata the shaper needs."""

    reference: str  # canonical top-level reference echo (e.g. "John 3:16-17")
    book_id: str
    book_name: str
    translations: tuple[str, ...]  # requested ids, in requested order
    rows: tuple[VerseRow, ...]


def get_verses(
    conn: sqlite3.Connection, reference: Reference, translation_ids: Sequence[str]
) -> QueryResult:
    """Fetch every verse of ``reference`` for the requested translations."""
    ids = tuple(translation_ids)
    rows = _collect(conn, reference.book_id, reference.spans, ids)
    return QueryResult(
        reference=reference.echo,
        book_id=reference.book_id,
        book_name=reference.book_name,
        translations=ids,
        rows=rows,
    )


def get_chapter(
    conn: sqlite3.Connection,
    book_id: str,
    book_name: str,
    chapter: int,
    translation_ids: Sequence[str],
) -> QueryResult:
    """Fetch a whole chapter for the requested translations."""
    ids = tuple(translation_ids)
    rows = _collect(conn, book_id, (Span(chapter, None, chapter, None),), ids)
    return QueryResult(
        reference=f"{book_name} {chapter}",
        book_id=book_id,
        book_name=book_name,
        translations=ids,
        rows=rows,
    )


def iter_verses(conn: sqlite3.Connection, translation_id: str) -> Iterator[VerseRow]:
    """Yield every verse of ``translation_id`` in canonical order (book, chapter, verse).

    A read-only bulk reader for whole-translation passes (e.g. building the semantic
    embeddings). Streams rows from the cursor, so callers iterate without holding the whole
    corpus in memory unless they choose to materialize it.
    """
    cursor = conn.execute(
        "SELECT v.book_id, v.chapter, v.verse, v.translation_id, v.text "
        "FROM verses v JOIN books b ON b.id = v.book_id "
        "WHERE v.translation_id = ? "
        "ORDER BY b.canonical_order, v.chapter, v.verse",
        (translation_id,),
    )
    for row in cursor:
        yield VerseRow(
            book_id=row["book_id"],
            chapter=row["chapter"],
            verse=row["verse"],
            translation_id=row["translation_id"],
            text=row["text"],
        )


def _collect(
    conn: sqlite3.Connection,
    book_id: str,
    spans: Sequence[Span],
    translation_ids: tuple[str, ...],
) -> tuple[VerseRow, ...]:
    if not translation_ids:
        return ()
    rows: list[VerseRow] = []
    for span in spans:
        rows.extend(_query_span(conn, book_id, span, translation_ids))
    return tuple(rows)


def _span_predicate(span: Span, chapter_col: str, verse_col: str) -> tuple[str, list[int]]:
    """SQL predicate + params matching a Span against the given chapter/verse columns.

    Shared by verse queries (``chapter``/``verse``), cross-ref queries
    (``from_chapter``/``from_verse``), and existence checks — one place defines the
    chapter-mode / same-chapter / cross-chapter linear-range logic.
    """
    if span.start_verse is None:  # whole-chapter / chapter-range
        return f"{chapter_col} BETWEEN ? AND ?", [span.start_chapter, span.end_chapter]
    assert span.end_verse is not None  # parser invariant: verse bounds are set together
    if span.start_chapter == span.end_chapter:  # same-chapter verse range
        return (
            f"{chapter_col} = ? AND {verse_col} BETWEEN ? AND ?",
            [span.start_chapter, span.start_verse, span.end_verse],
        )
    return (  # cross-chapter linear (chapter, verse) range
        f"({chapter_col} > ? OR ({chapter_col} = ? AND {verse_col} >= ?)) "
        f"AND ({chapter_col} < ? OR ({chapter_col} = ? AND {verse_col} <= ?))",
        [
            span.start_chapter,
            span.start_chapter,
            span.start_verse,
            span.end_chapter,
            span.end_chapter,
            span.end_verse,
        ],
    )


def _query_span(
    conn: sqlite3.Connection,
    book_id: str,
    span: Span,
    translation_ids: tuple[str, ...],
) -> list[VerseRow]:
    predicate, span_params = _span_predicate(span, "chapter", "verse")
    placeholders = ",".join("?" for _ in translation_ids)
    params: list[str | int] = [book_id, *span_params, *translation_ids]
    sql = (
        "SELECT book_id, chapter, verse, translation_id, text FROM verses "
        f"WHERE book_id = ? AND {predicate} AND translation_id IN ({placeholders}) "
        "ORDER BY chapter, verse, translation_id"
    )
    return [VerseRow(r[0], r[1], r[2], r[3], r[4]) for r in conn.execute(sql, params)]


def reference_exists(conn: sqlite3.Connection, reference: Reference) -> bool:
    """True if any translation has at least one verse within ``reference`` (bounds check).

    Used by the HTTP layer to distinguish a valid-but-cross-ref-less verse (200) from a
    verse out of canonical range in every translation (404).
    """
    for span in reference.spans:
        predicate, span_params = _span_predicate(span, "chapter", "verse")
        row = conn.execute(
            f"SELECT 1 FROM verses WHERE book_id = ? AND {predicate} LIMIT 1",
            [reference.book_id, *span_params],
        ).fetchone()
        if row is not None:
            return True
    return False


def get_verse_text(
    conn: sqlite3.Connection, translation_id: str, book_id: str, chapter: int, verse: int
) -> str | None:
    """Text of one verse in one translation, or ``None`` if absent there."""
    row = conn.execute(
        "SELECT text FROM verses WHERE translation_id = ? AND book_id = ? "
        "AND chapter = ? AND verse = ?",
        (translation_id, book_id, chapter, verse),
    ).fetchone()
    return None if row is None else row[0]


# --- full-text search (FTS5) ---------------------------------------------------------

# Markers wrapped around matched terms in the snippet (semantic HTML; easy to transform).
SEARCH_MARK_OPEN = "<mark>"
SEARCH_MARK_CLOSE = "</mark>"
SNIPPET_TOKENS = 32  # snippet window; short verses show in full, long ones are windowed


class SearchQueryError(Exception):
    """The FTS5 MATCH expression is malformed (mapped to HTTP 400 by the API)."""


@dataclass(frozen=True)
class SearchHit:
    """One search match: its position, canonical book name, and highlighted snippet."""

    book_id: str
    book_name: str
    chapter: int
    verse: int
    snippet: str


@dataclass(frozen=True)
class SearchPage:
    """A page of hits plus the total match count (for pagination metadata)."""

    hits: tuple[SearchHit, ...]
    total: int


def search_verses(
    conn: sqlite3.Connection,
    query: str,
    translation_id: str,
    book_id: str | None,
    limit: int,
    offset: int,
) -> SearchPage:
    """Full-text search one translation, optionally filtered to one book.

    Relevance-ranked (FTS5 ``rank``) with a canonical tiebreak, so successive
    ``limit``/``offset`` pages don't overlap. Returns the page plus the total match count
    (a second query). Raises :class:`SearchQueryError` if the MATCH expression is invalid.
    """
    book_filter = " AND v.book_id = ?" if book_id is not None else ""
    base_params: list[str] = [query, translation_id]
    if book_id is not None:
        base_params.append(book_id)

    snippet_fn = (
        f"snippet(verses_fts, 0, '{SEARCH_MARK_OPEN}', "
        f"'{SEARCH_MARK_CLOSE}', '…', {SNIPPET_TOKENS})"
    )
    hits_sql = (
        f"SELECT v.book_id, b.name, v.chapter, v.verse, {snippet_fn} "
        "FROM verses_fts f "
        "JOIN verses v ON v.id = f.rowid "
        "JOIN books b ON b.id = v.book_id "
        f"WHERE verses_fts MATCH ? AND v.translation_id = ?{book_filter} "
        "ORDER BY f.rank, b.canonical_order, v.chapter, v.verse "
        "LIMIT ? OFFSET ?"
    )
    count_sql = (
        "SELECT COUNT(*) FROM verses_fts f "
        "JOIN verses v ON v.id = f.rowid "
        f"WHERE verses_fts MATCH ? AND v.translation_id = ?{book_filter}"
    )

    try:
        hit_rows = conn.execute(hits_sql, [*base_params, limit, offset]).fetchall()
        total = conn.execute(count_sql, base_params).fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise SearchQueryError(str(exc)) from exc

    hits = tuple(SearchHit(r[0], r[1], r[2], r[3], r[4]) for r in hit_rows)
    return SearchPage(hits=hits, total=total)


# --- cross-references ----------------------------------------------------------------


@dataclass(frozen=True)
class CrossRefRow:
    """One cross-reference: a source verse → a target verse or same-chapter range."""

    from_book_id: str
    from_book_name: str
    from_chapter: int
    from_verse: int
    to_book_id: str
    to_book_name: str
    to_chapter: int
    to_verse_start: int
    to_verse_end: int | None  # None ⇒ single verse (or a clamped multi-chapter target)
    votes: int | None


@dataclass(frozen=True)
class CrossRefPage:
    """A page of cross-references plus the total match count."""

    rows: tuple[CrossRefRow, ...]
    total: int


def get_cross_references(
    conn: sqlite3.Connection,
    reference: Reference,
    min_votes: int,
    limit: int,
    offset: int,
) -> CrossRefPage:
    """Cross-references whose source verse falls within ``reference``, votes ≥ ``min_votes``.

    Ordered by votes desc with a canonical tiebreak (so pages don't overlap); ``total`` is
    a separate count across the whole reference.
    """
    clauses: list[str] = []
    params: list[str | int] = [reference.book_id]
    for span in reference.spans:
        predicate, span_params = _span_predicate(span, "from_chapter", "from_verse")
        clauses.append(f"({predicate})")
        params += span_params
    where = f"from_book_id = ? AND ({' OR '.join(clauses)}) AND votes >= ?"
    params.append(min_votes)

    hits_sql = (
        "SELECT x.from_book_id, bf.name, x.from_chapter, x.from_verse, "
        "x.to_book_id, bt.name, x.to_chapter, x.to_verse_start, x.to_verse_end, x.votes "
        "FROM cross_references x "
        "JOIN books bf ON bf.id = x.from_book_id "
        "JOIN books bt ON bt.id = x.to_book_id "
        f"WHERE {where} "
        "ORDER BY x.votes DESC, bf.canonical_order, x.from_chapter, x.from_verse, "
        "bt.canonical_order, x.to_chapter, x.to_verse_start "
        "LIMIT ? OFFSET ?"
    )
    rows = tuple(
        CrossRefRow(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9])
        for r in conn.execute(hits_sql, [*params, limit, offset])
    )
    total = conn.execute(f"SELECT COUNT(*) FROM cross_references WHERE {where}", params).fetchone()[
        0
    ]
    return CrossRefPage(rows=rows, total=total)


# --- translator's notes (v4) ---------------------------------------------------------


@dataclass(frozen=True)
class NoteCrossRefRow:
    """One cross-reference carried by a note → a target verse or range (canonical coords)."""

    to_book_id: str
    to_book_name: str
    to_chapter: int
    to_verse_start: int
    to_verse_end: int | None  # None ⇒ single verse


@dataclass(frozen=True)
class NoteRow:
    """One translator's note for a passage, with its own cross-references nested."""

    id: int
    book_id: str
    book_name: str
    chapter: int
    verse: int
    note_type: str | None
    text: str
    char_offset: int
    marker: str | None
    ordinal: int
    cross_references: tuple[NoteCrossRefRow, ...]


def get_notes(
    conn: sqlite3.Connection,
    translation_id: str,
    book_id: str,
    chapter: int,
    verse: int | None = None,
) -> tuple[NoteRow, ...]:
    """Notes for a chapter (or one verse) in a translation, ordered verse → ordinal → id.

    Unpaginated — a chapter's notes are bounded (mirrors ``get_places_for_reference``). A
    translation with no notes for the passage simply returns ``()`` — the caller serves that as
    an empty list (200), never a 404.
    """
    params: list[str | int] = [translation_id, book_id, chapter]
    verse_clause = ""
    if verse is not None:
        verse_clause = " AND n.verse = ?"
        params.append(verse)

    note_sql = (
        "SELECT n.id, n.book_id, b.name, n.chapter, n.verse, n.note_type, n.text, "
        "n.char_offset, n.marker, n.ordinal "
        "FROM translator_notes n JOIN books b ON b.id = n.book_id "
        f"WHERE n.translation_id = ? AND n.book_id = ? AND n.chapter = ?{verse_clause} "
        "ORDER BY n.verse, n.ordinal, n.id"
    )
    note_rows = conn.execute(note_sql, params).fetchall()
    if not note_rows:
        return ()

    ids = [r[0] for r in note_rows]
    placeholders = ",".join("?" * len(ids))
    xref_sql = (
        "SELECT x.note_id, x.to_book_id, b.name, x.to_chapter, x.to_verse_start, x.to_verse_end "
        "FROM note_cross_references x JOIN books b ON b.id = x.to_book_id "
        f"WHERE x.note_id IN ({placeholders}) ORDER BY x.note_id, x.id"
    )
    by_note: dict[int, list[NoteCrossRefRow]] = defaultdict(list)
    for r in conn.execute(xref_sql, ids):
        by_note[r[0]].append(NoteCrossRefRow(r[1], r[2], r[3], r[4], r[5]))

    return tuple(
        NoteRow(
            r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], tuple(by_note.get(r[0], ()))
        )
        for r in note_rows
    )


# --- metadata + random ---------------------------------------------------------------


@dataclass(frozen=True)
class BookMeta:
    """A book's catalog metadata."""

    id: str
    name: str
    testament: str
    canonical_order: int
    chapter_count: int | None


@dataclass(frozen=True)
class TranslationMeta:
    """A loaded translation's catalog metadata."""

    id: str
    name: str
    language: str
    versification: str
    attribution: str | None


@dataclass(frozen=True)
class RandomVerse:
    """One verse picked at random."""

    book_id: str
    book_name: str
    chapter: int
    verse: int
    text: str


def get_books(conn: sqlite3.Connection) -> list[BookMeta]:
    """All books in canonical order."""
    return [
        BookMeta(r[0], r[1], r[2], r[3], r[4])
        for r in conn.execute(
            "SELECT id, name, testament, canonical_order, chapter_count "
            "FROM books ORDER BY canonical_order"
        )
    ]


def get_translations(conn: sqlite3.Connection) -> list[TranslationMeta]:
    """All loaded translations, ordered by id."""
    return [
        TranslationMeta(r[0], r[1], r[2], r[3], r[4])
        for r in conn.execute(
            "SELECT id, name, language, versification, attribution FROM translations ORDER BY id"
        )
    ]


def get_random_verse(
    conn: sqlite3.Connection,
    translation_id: str,
    book_id: str | None,
    testament: str | None,
) -> RandomVerse | None:
    """One random verse in ``translation_id``, optionally filtered by book and/or testament.

    Returns ``None`` when the filters match no verse (e.g. ``book`` and ``testament``
    contradict). ``ORDER BY RANDOM()`` scans the matching rows — fine at this scale.
    """
    clauses = ["v.translation_id = ?"]
    params: list[str] = [translation_id]
    if book_id is not None:
        clauses.append("v.book_id = ?")
        params.append(book_id)
    if testament is not None:
        clauses.append("b.testament = ?")
        params.append(testament)

    row = conn.execute(
        "SELECT v.book_id, b.name, v.chapter, v.verse, v.text "
        "FROM verses v JOIN books b ON b.id = v.book_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY RANDOM() LIMIT 1",
        params,
    ).fetchone()
    return None if row is None else RandomVerse(row[0], row[1], row[2], row[3], row[4])


# --- geography (v3): places + the bi-directional place↔verse link ---------------------


@dataclass(frozen=True)
class PlaceRow:
    """One biblical place. Coordinates/confidence are ``None`` for places with no confident
    location (unknown/symbolic/multiple) — the honesty model (SPEC v3 §6)."""

    id: str
    friendly_id: str
    name: str
    url_slug: str
    type: str
    preceding_article: str
    latitude: float | None
    longitude: float | None
    confidence: str | None
    confidence_score: int | None
    status: str
    modern_name: str | None


@dataclass(frozen=True)
class PlacePage:
    """A page of places plus the total match count."""

    rows: tuple[PlaceRow, ...]
    total: int


@dataclass(frozen=True)
class PlaceVerseRef:
    """One verse a place is mentioned in (book id + name for reference formatting)."""

    book_id: str
    book_name: str
    chapter: int
    verse: int


# The places columns, in schema order; bare and ``p.``-prefixed (for the join query).
_PLACE_COLS = (
    "id",
    "friendly_id",
    "name",
    "url_slug",
    "type",
    "preceding_article",
    "latitude",
    "longitude",
    "confidence",
    "confidence_score",
    "status",
    "modern_name",
)
_PLACE_SELECT = ", ".join(_PLACE_COLS)


def _row_to_place(r: sqlite3.Row) -> PlaceRow:
    return PlaceRow(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11])


def list_places(
    conn: sqlite3.Connection,
    type_filter: str | None,
    status_filter: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> PlacePage:
    """Browse places, optionally filtered by ``type``/``status``/name substring (``q``).

    Ordered ``name, id`` (a stable tiebreak so same-named places paginate deterministically);
    ``total`` is a separate count over the same filter.
    """
    clauses: list[str] = []
    params: list[str] = []
    if type_filter is not None:
        clauses.append("type = ?")
        params.append(type_filter)
    if status_filter is not None:
        clauses.append("status = ?")
        params.append(status_filter)
    if q is not None and q.strip():
        clauses.append("name LIKE '%' || ? || '%'")  # case-insensitive for ASCII names
        params.append(q.strip())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = tuple(
        _row_to_place(r)
        for r in conn.execute(
            f"SELECT {_PLACE_SELECT} FROM places{where} ORDER BY name, id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
    )
    total = conn.execute(f"SELECT COUNT(*) FROM places{where}", params).fetchone()[0]
    return PlacePage(rows=rows, total=total)


def get_place(conn: sqlite3.Connection, place_id: str) -> PlaceRow | None:
    """One place by its stable id, or ``None`` if no such place."""
    row = conn.execute(f"SELECT {_PLACE_SELECT} FROM places WHERE id = ?", (place_id,)).fetchone()
    return None if row is None else _row_to_place(row)


def count_place_verses(conn: sqlite3.Connection, place_id: str) -> int:
    """How many verses mention this place."""
    return conn.execute(
        "SELECT COUNT(*) FROM place_verses WHERE place_id = ?", (place_id,)
    ).fetchone()[0]


def get_place_verses(
    conn: sqlite3.Connection, place_id: str, limit: int, offset: int
) -> tuple[tuple[PlaceVerseRef, ...], int]:
    """The verses mentioning ``place_id``, in canonical order, plus the total count."""
    rows = tuple(
        PlaceVerseRef(r[0], r[1], r[2], r[3])
        for r in conn.execute(
            "SELECT pv.book_id, b.name, pv.chapter, pv.verse "
            "FROM place_verses pv JOIN books b ON b.id = pv.book_id "
            "WHERE pv.place_id = ? "
            "ORDER BY b.canonical_order, pv.chapter, pv.verse "
            "LIMIT ? OFFSET ?",
            (place_id, limit, offset),
        )
    )
    total = count_place_verses(conn, place_id)
    return rows, total


def get_places_for_reference(conn: sqlite3.Connection, reference: Reference) -> PlacePage:
    """The distinct places mentioned anywhere in ``reference`` (the union across its spans).

    The inverse of ``get_place_verses``. ``SELECT DISTINCT`` dedups a place named in several
    verses of the range; ordered ``name, id``. No pagination (a reference spans few places).
    """
    clauses: list[str] = []
    params: list[str | int] = [reference.book_id]
    for span in reference.spans:
        predicate, span_params = _span_predicate(span, "pv.chapter", "pv.verse")
        clauses.append(f"({predicate})")
        params += span_params
    where = f"pv.book_id = ? AND ({' OR '.join(clauses)})"

    cols = ", ".join(f"p.{c}" for c in _PLACE_COLS)
    rows = tuple(
        _row_to_place(r)
        for r in conn.execute(
            f"SELECT DISTINCT {cols} "
            "FROM places p JOIN place_verses pv ON pv.place_id = p.id "
            f"WHERE {where} ORDER BY p.name, p.id",
            params,
        )
    )
    return PlacePage(rows=rows, total=len(rows))


def distinct_place_types(conn: sqlite3.Connection) -> list[str]:
    """The set of place ``type`` values present, sorted — for validating a ``?type=`` filter."""
    return [r[0] for r in conn.execute("SELECT DISTINCT type FROM places ORDER BY type")]
