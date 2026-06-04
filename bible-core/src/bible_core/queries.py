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
