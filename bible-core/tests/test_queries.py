"""Query layer: Span → SQL mapping for every grammar form, plus missing/empty cases."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from bible_core.parser import parse_reference
from bible_core.queries import QueryResult, get_chapter, get_verses
from bible_core.resolver import SqliteBookResolver
from bible_core.schema import create_schema
from bible_core.seed import seed_books


def _build() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    seed_books(conn)
    for tid in ("KJV", "WEB"):
        conn.execute(
            "INSERT INTO translations (id, name, language, direction, versification, attribution) "
            "VALUES (?, ?, 'en', 'ltr', 'standard', 'PD')",
            (tid, tid),
        )
    rows: list[tuple[str, str, int, int, str]] = []
    for tid in ("KJV", "WEB"):
        for verse in range(1, 21):
            if tid == "WEB" and verse == 16:  # WEB omits John 3:16
                continue
            rows.append((tid, "JHN", 3, verse, f"JHN 3:{verse} ({tid})"))
        for verse in range(1, 11):
            rows.append((tid, "JHN", 4, verse, f"JHN 4:{verse} ({tid})"))
    conn.executemany(
        "INSERT INTO verses (translation_id, book_id, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return conn


CONN = _build()


def _verses(ref: str, ids: Sequence[str] = ("KJV",)) -> QueryResult:
    reference = parse_reference(ref, SqliteBookResolver(CONN))
    return get_verses(CONN, reference, ids)


def _positions(result: QueryResult) -> list[tuple[int, int]]:
    return sorted({(row.chapter, row.verse) for row in result.rows})


def test_single_verse() -> None:
    assert _positions(_verses("John 3:16")) == [(3, 16)]


def test_verse_range() -> None:
    assert _positions(_verses("John 3:16-18")) == [(3, 16), (3, 17), (3, 18)]


def test_verse_list() -> None:
    assert _positions(_verses("John 3:16,18,20")) == [(3, 16), (3, 18), (3, 20)]


def test_whole_chapter() -> None:
    assert _positions(_verses("John 3")) == [(3, v) for v in range(1, 21)]


def test_chapter_range() -> None:
    result = _verses("John 3-4")
    assert {row.chapter for row in result.rows} == {3, 4}
    assert len([r for r in result.rows if r.chapter == 4]) == 10


def test_cross_chapter_linear_range() -> None:
    assert _positions(_verses("John 3:18-4:2")) == [(3, 18), (3, 19), (3, 20), (4, 1), (4, 2)]


def test_get_chapter() -> None:
    result = get_chapter(CONN, "JHN", "John", 4, ("KJV",))
    assert result.reference == "John 4"
    assert len(result.rows) == 10


def test_missing_verse_only_present_translation_returns_rows() -> None:
    result = _verses("John 3:16", ("KJV", "WEB"))
    assert {row.translation_id for row in result.rows} == {"KJV"}  # WEB omitted


def test_out_of_range_is_empty() -> None:
    assert _verses("Genesis 999:1").rows == ()


def test_huge_range_stays_a_single_cheap_query() -> None:
    # Chapter 1 isn't loaded; the point is this returns instantly (no materialization).
    assert _verses("John 1:1-99999999").rows == ()
