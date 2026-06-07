"""Multi-translation FTS5 search: dedup by canonical verse, the per-translation matches, max-
relevance ranking, canonical tiebreak, pagination over verses, errors. The companion to
test_search.py (single-translation) — search_verses is intentionally untouched by S2.

Synthetic verses only. Deterministic text per (verse, translation) drives exact assertions.
"""

from __future__ import annotations

import sqlite3

import pytest
from bible_core.queries import SearchQueryError, search_verses_multi
from bible_core.schema import create_schema
from bible_core.seed import seed_books


def _build() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    seed_books(conn)
    conn.executemany(
        "INSERT INTO translations (id, name, language, direction, versification, attribution) "
        "VALUES (?, ?, 'en', 'ltr', 'standard', 'PD')",
        [("KJV", "King James Version"), ("WEB", "World English Bible"), ("YLT", "Young's")],
    )
    # "<BOOK> <ch>:<vs> <TID> word" — "word" matches every verse/translation; "<TID>" matches only
    # that translation; so the matches map per verse is predictable. WEB omits GEN 1:2 (one verse
    # that matches in fewer translations).
    rows: list[tuple[str, str, int, int, str]] = []
    for tid in ("KJV", "WEB", "YLT"):
        for book, chapter, verse in (
            ("GEN", 1, 1),
            ("GEN", 1, 2),
            ("GEN", 1, 3),
            ("JHN", 3, 16),
        ):
            if tid == "WEB" and (book, chapter, verse) == ("GEN", 1, 2):
                continue
            rows.append((tid, book, chapter, verse, f"{book} {chapter}:{verse} {tid} word"))
    conn.executemany(
        "INSERT INTO verses (translation_id, book_id, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")
    conn.commit()
    return conn


CONN = _build()
ALL = ("KJV", "WEB", "YLT")


def test_dedup_one_hit_per_canonical_verse() -> None:
    page = search_verses_multi(CONN, "word", ALL, None, 20, 0)
    keys = [(h.book_id, h.chapter, h.verse) for h in page.hits]
    assert len(keys) == len(set(keys)) == 4  # GEN 1:1-3 + JHN 3:16, each once
    assert page.total == 4


def test_matches_map_per_verse() -> None:
    page = search_verses_multi(CONN, "word", ALL, None, 20, 0)
    by_key = {(h.book_id, h.chapter, h.verse): h for h in page.hits}
    # GEN 1:1 matched in all three; GEN 1:2 only KJV+YLT (WEB omits it).
    assert {m.translation_id for m in by_key[("GEN", 1, 1)].matches} == {"KJV", "WEB", "YLT"}
    assert {m.translation_id for m in by_key[("GEN", 1, 2)].matches} == {"KJV", "YLT"}


def test_total_counts_verses_not_pairs() -> None:
    # "word" matches 11 (verse, translation) rows but only 4 distinct canonical verses.
    page = search_verses_multi(CONN, "word", ALL, None, 20, 0)
    assert page.total == 4


def test_snippet_has_markers() -> None:
    page = search_verses_multi(CONN, "word", ALL, None, 20, 0)
    assert all("<mark>word</mark>" in m.snippet for h in page.hits for m in h.matches)


def test_single_translation_match_yields_one_entry() -> None:
    # "kjv" is a literal token only in KJV verses → each hit's matches has exactly one entry.
    page = search_verses_multi(CONN, "kjv", ALL, None, 20, 0)
    assert all([m.translation_id for m in h.matches] == ["KJV"] for h in page.hits)


def test_canonical_tiebreak_orders_pages() -> None:
    page = search_verses_multi(CONN, "word", ALL, None, 20, 0)
    # Equal relevance across verses → canonical order: GEN before JHN, ascending verse.
    assert [(h.book_id, h.chapter, h.verse) for h in page.hits] == [
        ("GEN", 1, 1),
        ("GEN", 1, 2),
        ("GEN", 1, 3),
        ("JHN", 3, 16),
    ]


def test_pagination_over_verses_non_overlapping() -> None:
    page1 = search_verses_multi(CONN, "word", ALL, None, 2, 0)
    page2 = search_verses_multi(CONN, "word", ALL, None, 2, 2)
    keys1 = {(h.book_id, h.chapter, h.verse) for h in page1.hits}
    keys2 = {(h.book_id, h.chapter, h.verse) for h in page2.hits}
    assert len(keys1) == len(keys2) == 2
    assert not (keys1 & keys2)
    assert page1.total == page2.total == 4


def test_book_filter() -> None:
    page = search_verses_multi(CONN, "word", ALL, "GEN", 20, 0)
    assert page.total == 3
    assert all(h.book_id == "GEN" for h in page.hits)


def test_subset_of_translations() -> None:
    page = search_verses_multi(CONN, "word", ("KJV", "YLT"), None, 20, 0)
    by_key = {(h.book_id, h.chapter, h.verse): h for h in page.hits}
    assert {m.translation_id for m in by_key[("GEN", 1, 1)].matches} == {"KJV", "YLT"}


def test_zero_matches() -> None:
    page = search_verses_multi(CONN, "zebra", ALL, None, 20, 0)
    assert page.hits == ()
    assert page.total == 0


def test_offset_beyond_total() -> None:
    page = search_verses_multi(CONN, "word", ALL, None, 20, 100)
    assert page.hits == ()
    assert page.total == 4


def test_malformed_query_raises() -> None:
    with pytest.raises(SearchQueryError):
        search_verses_multi(CONN, '"unbalanced', ALL, None, 20, 0)
