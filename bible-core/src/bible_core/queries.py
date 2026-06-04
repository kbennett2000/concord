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
from collections.abc import Sequence
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
