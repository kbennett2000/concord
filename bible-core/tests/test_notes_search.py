"""FTS5 notes search: hits, total, snippet markers, translation/type/book filters, ordering,
pagination, errors. The direct analogue of test_search.py over the notes_fts mirror.

Licensing-clean: a handful of synthetic notes in real book slots (never copyrighted NET data).
"""

from __future__ import annotations

import sqlite3

import pytest
from bible_core.queries import SearchQueryError, search_notes
from bible_core.schema import create_schema
from bible_core.seed import seed_books


def _build() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    seed_books(conn)
    conn.executemany(
        "INSERT INTO translations (id, name, language, direction, versification, attribution) "
        "VALUES (?, ?, 'en', 'ltr', 'standard', 'PD')",
        [("KJV", "King James Version"), ("NET", "New English Translation")],
    )
    # (id, translation_id, book_id, chapter, verse, note_type, text, char_offset, marker, ordinal)
    notes = [
        (1, "KJV", "GEN", 1, 1, "tn", "A note on the beginning.", 0, None, 1),
        (2, "KJV", "JHN", 3, 16, "sn", "A note about love.", 0, "a", 1),
        (3, "KJV", "JHN", 3, 16, "tc", "A textual variant note here.", 0, "b", 2),
        (4, "NET", "PSA", 119, 105, "tn", "A note about a lamp unto my feet.", 0, None, 1),
        # Identical bodies in two books → tie on rank; canonical order (GEN before JHN) decides.
        (5, "KJV", "GEN", 2, 1, "tn", "Shared tiebreak token zeta.", 0, None, 1),
        (6, "KJV", "JHN", 5, 1, "tn", "Shared tiebreak token zeta.", 0, None, 1),
        # Identical bodies in one verse → tie on rank; ordinal decides.
        (7, "KJV", "1JN", 1, 1, "tn", "Order token kappa.", 0, None, 1),
        (8, "KJV", "1JN", 1, 1, "sn", "Order token kappa.", 0, None, 2),
    ]
    conn.executemany(
        "INSERT INTO translator_notes "
        "(id, translation_id, book_id, chapter, verse, note_type, text, char_offset, "
        "marker, ordinal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        notes,
    )
    conn.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
    conn.commit()
    return conn


CONN = _build()


def test_single_word_hits() -> None:
    page = search_notes(CONN, "note", None, None, None, 20, 0)
    assert page.total == 4  # notes 1-4 each contain the token "note"
    assert {(h.book_id, h.chapter, h.verse) for h in page.hits} == {
        ("GEN", 1, 1),
        ("JHN", 3, 16),
        ("PSA", 119, 105),
    }


def test_phrase_match() -> None:
    page = search_notes(CONN, '"about love"', None, None, None, 20, 0)
    assert page.total == 1
    assert (page.hits[0].book_id, page.hits[0].verse) == ("JHN", 16)


def test_snippet_has_markers() -> None:
    page = search_notes(CONN, "lamp", None, None, None, 20, 0)
    assert "<mark>lamp</mark>" in page.hits[0].snippet


def test_hit_carries_anchor_and_translation() -> None:
    page = search_notes(CONN, "lamp", None, None, None, 20, 0)
    hit = page.hits[0]
    assert (hit.book_id, hit.book_name, hit.chapter, hit.verse) == ("PSA", "Psalms", 119, 105)
    assert (hit.translation_id, hit.note_type, hit.char_offset, hit.marker, hit.ordinal) == (
        "NET",
        "tn",
        0,
        None,
        1,
    )


def test_translation_filter() -> None:
    page = search_notes(CONN, "note", "NET", None, None, 20, 0)
    assert page.total == 1
    assert page.hits[0].translation_id == "NET"


def test_type_filter() -> None:
    page = search_notes(CONN, "note", None, "tc", None, 20, 0)
    assert page.total == 1
    assert page.hits[0].note_type == "tc"


def test_book_filter() -> None:
    page = search_notes(CONN, "note", None, None, "JHN", 20, 0)
    assert page.total == 2
    assert {h.book_id for h in page.hits} == {"JHN"}


def test_canonical_tiebreak_across_books() -> None:
    page = search_notes(CONN, "zeta", None, None, None, 20, 0)
    assert [h.book_id for h in page.hits] == ["GEN", "JHN"]  # canonical order on equal rank


def test_ordinal_tiebreak_within_verse() -> None:
    page = search_notes(CONN, "kappa", None, None, None, 20, 0)
    assert [(h.book_id, h.verse, h.ordinal) for h in page.hits] == [
        ("1JN", 1, 1),
        ("1JN", 1, 2),
    ]


def test_total_is_independent_of_limit() -> None:
    page = search_notes(CONN, "note", None, None, None, 1, 0)
    assert len(page.hits) == 1
    assert page.total == 4


def test_pagination_does_not_overlap() -> None:
    page1 = search_notes(CONN, "note", None, None, None, 2, 0)
    page2 = search_notes(CONN, "note", None, None, None, 2, 2)
    keys1 = {(h.book_id, h.chapter, h.verse, h.ordinal) for h in page1.hits}
    keys2 = {(h.book_id, h.chapter, h.verse, h.ordinal) for h in page2.hits}
    assert not (keys1 & keys2)


def test_zero_matches() -> None:
    page = search_notes(CONN, "zebra", None, None, None, 20, 0)
    assert page.hits == ()
    assert page.total == 0


def test_malformed_query_raises() -> None:
    with pytest.raises(SearchQueryError):
        search_notes(CONN, '"unbalanced', None, None, None, 20, 0)
