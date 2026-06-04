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


def _query_span(
    conn: sqlite3.Connection,
    book_id: str,
    span: Span,
    translation_ids: tuple[str, ...],
) -> list[VerseRow]:
    params: list[str | int | None] = [book_id]
    if span.start_verse is None:  # whole-chapter / chapter-range
        predicate = "chapter BETWEEN ? AND ?"
        params += [span.start_chapter, span.end_chapter]
    elif span.start_chapter == span.end_chapter:  # same-chapter verse range
        predicate = "chapter = ? AND verse BETWEEN ? AND ?"
        params += [span.start_chapter, span.start_verse, span.end_verse]
    else:  # cross-chapter linear (chapter, verse) range
        predicate = (
            "(chapter > ? OR (chapter = ? AND verse >= ?)) "
            "AND (chapter < ? OR (chapter = ? AND verse <= ?))"
        )
        params += [
            span.start_chapter,
            span.start_chapter,
            span.start_verse,
            span.end_chapter,
            span.end_chapter,
            span.end_verse,
        ]

    placeholders = ",".join("?" for _ in translation_ids)
    params += list(translation_ids)
    sql = (
        "SELECT book_id, chapter, verse, translation_id, text FROM verses "
        f"WHERE book_id = ? AND {predicate} AND translation_id IN ({placeholders}) "
        "ORDER BY chapter, verse, translation_id"
    )
    return [VerseRow(r[0], r[1], r[2], r[3], r[4]) for r in conn.execute(sql, params)]


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
