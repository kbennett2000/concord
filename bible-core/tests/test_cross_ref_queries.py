"""get_cross_references, reference_exists, and get_verse_text."""

from __future__ import annotations

import sqlite3

from bible_core.parser import parse_reference
from bible_core.queries import get_cross_references, get_verse_text, reference_exists
from bible_core.resolver import SqliteBookResolver
from bible_core.schema import create_schema
from bible_core.seed import seed_books


def _build() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    seed_books(conn)
    conn.execute(
        "INSERT INTO translations (id, name, language, direction, versification, attribution) "
        "VALUES ('KJV', 'KJV', 'en', 'ltr', 'standard', 'PD')"
    )
    conn.executemany(
        "INSERT INTO verses (translation_id, book_id, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
        [("KJV", "JHN", 3, v, f"JHN 3:{v} (KJV)") for v in range(1, 21)]
        + [("KJV", "GEN", 1, v, f"GEN 1:{v} (KJV)") for v in range(1, 4)],
    )
    conn.executemany(
        "INSERT INTO cross_references "
        "(from_book_id, from_chapter, from_verse, to_book_id, to_chapter, "
        "to_verse_start, to_verse_end, votes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("JHN", 3, 16, "GEN", 1, 1, None, 50),
            ("JHN", 3, 16, "GEN", 1, 2, None, 30),
            ("JHN", 3, 16, "GEN", 1, 3, None, 5),
            ("JHN", 3, 17, "GEN", 1, 1, None, 10),
        ],
    )
    conn.commit()
    return conn


CONN = _build()


def _ref(text: str):  # noqa: ANN202 - test helper
    return parse_reference(text, SqliteBookResolver(CONN))


def test_orders_by_votes_desc_with_total() -> None:
    page = get_cross_references(CONN, _ref("John 3:16"), 0, 20, 0)
    assert page.total == 3
    assert [r.votes for r in page.rows] == [50, 30, 5]
    assert page.rows[0].to_book_name == "Genesis"


def test_min_votes_filter() -> None:
    page = get_cross_references(CONN, _ref("John 3:16"), 10, 20, 0)
    assert page.total == 2
    assert all((r.votes or 0) >= 10 for r in page.rows)


def test_range_input_spans_source_verses() -> None:
    page = get_cross_references(CONN, _ref("John 3:16-17"), 0, 20, 0)
    assert page.total == 4  # 3 from v16 + 1 from v17


def test_pagination_no_overlap() -> None:
    page1 = get_cross_references(CONN, _ref("John 3:16"), 0, 2, 0)
    page2 = get_cross_references(CONN, _ref("John 3:16"), 0, 2, 2)
    keys1 = {(r.to_chapter, r.to_verse_start) for r in page1.rows}
    keys2 = {(r.to_chapter, r.to_verse_start) for r in page2.rows}
    assert len(page1.rows) == 2
    assert len(page2.rows) == 1
    assert not (keys1 & keys2)


def test_reference_exists() -> None:
    assert reference_exists(CONN, _ref("John 3:16")) is True
    assert reference_exists(CONN, _ref("Genesis 999:1")) is False


def test_get_verse_text() -> None:
    assert get_verse_text(CONN, "KJV", "GEN", 1, 1) == "GEN 1:1 (KJV)"
    assert get_verse_text(CONN, "KJV", "GEN", 99, 1) is None
