"""FTS5 search query: hits, total, snippet markers, book filter, pagination, errors."""

from __future__ import annotations

import sqlite3

import pytest
from bible_core.queries import SearchQueryError, search_verses
from bible_core.schema import create_schema
from bible_core.seed import seed_books


def _build() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    seed_books(conn)
    conn.execute(
        "INSERT INTO translations (id, name, language, direction, versification, attribution) "
        "VALUES ('KJV', 'King James Version', 'en', 'ltr', 'standard', 'PD')"
    )
    rows = [
        ("KJV", "GEN", 1, 1, "In the beginning God created the heaven and the earth."),
        ("KJV", "JHN", 1, 1, "In the beginning was the Word, and the Word was with God."),
        ("KJV", "JHN", 3, 16, "For God so loved the world."),
        ("KJV", "PSA", 119, 105, "Thy word is a lamp unto my feet, and a light unto my path."),
    ]
    conn.executemany(
        "INSERT INTO verses (translation_id, book_id, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")
    conn.commit()
    return conn


CONN = _build()


def test_single_word_hits() -> None:
    page = search_verses(CONN, "beginning", "KJV", None, 20, 0)
    assert page.total == 2
    assert {(h.book_id, h.chapter, h.verse) for h in page.hits} == {("GEN", 1, 1), ("JHN", 1, 1)}


def test_snippet_has_markers() -> None:
    page = search_verses(CONN, "lamp", "KJV", None, 20, 0)
    assert "<mark>lamp</mark>" in page.hits[0].snippet


def test_hit_carries_canonical_book_name() -> None:
    page = search_verses(CONN, "lamp", "KJV", None, 20, 0)
    assert page.hits[0].book_name == "Psalms"


def test_book_filter() -> None:
    page = search_verses(CONN, "God", "KJV", "GEN", 20, 0)
    assert {h.book_id for h in page.hits} == {"GEN"}
    assert page.total == 1


def test_total_is_independent_of_limit() -> None:
    page = search_verses(CONN, "God", "KJV", None, 1, 0)
    assert len(page.hits) == 1
    assert page.total == 3  # GEN 1:1, JHN 1:1, JHN 3:16


def test_pagination_does_not_overlap() -> None:
    page1 = search_verses(CONN, "the", "KJV", None, 2, 0)
    page2 = search_verses(CONN, "the", "KJV", None, 2, 2)
    keys1 = {(h.book_id, h.chapter, h.verse) for h in page1.hits}
    keys2 = {(h.book_id, h.chapter, h.verse) for h in page2.hits}
    assert not (keys1 & keys2)


def test_zero_matches() -> None:
    page = search_verses(CONN, "zebra", "KJV", None, 20, 0)
    assert page.hits == ()
    assert page.total == 0


def test_malformed_query_raises() -> None:
    with pytest.raises(SearchQueryError):
        search_verses(CONN, '"unbalanced', "KJV", None, 20, 0)
