"""Exhaustive tests for the book-token normalizer (canonical-books.md contract)."""

from __future__ import annotations

import pytest
from bible_core.normalize import normalize

CASES = [
    # lowercase
    ("Genesis", "genesis"),
    ("GENESIS", "genesis"),
    ("gEnEsIs", "genesis"),
    # punctuation: periods and apostrophes stripped
    ("Jn.", "jn"),
    ("1 Jn.", "1jn"),
    ("St. John", "stjohn"),
    ("O'Book", "obook"),
    ("O’Book", "obook"),  # curly apostrophe
    # internal whitespace removed
    ("1 sam", "1sam"),
    ("song of songs", "songofsongs"),
    ("  song   of   songs  ", "songofsongs"),
    ("Song of Solomon", "songofsolomon"),
    # leading ordinal -> digit, every casing and form
    ("I Samuel", "1samuel"),
    ("i samuel", "1samuel"),
    ("II Kings", "2kings"),
    ("ii kings", "2kings"),
    ("III John", "3john"),
    ("iii john", "3john"),
    ("First John", "1john"),
    ("first john", "1john"),
    ("FIRST JOHN", "1john"),
    ("Second Kings", "2kings"),
    ("SECOND kings", "2kings"),
    ("Third John", "3john"),
    ("1 John", "1john"),
    ("1John", "1john"),
    ("2 Corinthians", "2corinthians"),
    # the critical non-ordinal cases: a leading i/ii must NOT be mangled mid-word
    ("Isaiah", "isaiah"),
    ("Isa", "isa"),
    ("Ii", "ii"),  # bare ordinal token alone is left as-is (no following name)
    ("First", "first"),
    # already-normalized digit forms pass through unchanged
    ("1samuel", "1samuel"),
    ("2kings", "2kings"),
    ("jud", "jud"),
    # whitespace-only / empty
    ("", ""),
    ("   ", ""),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_normalize_is_idempotent(raw: str, expected: str) -> None:
    assert normalize(normalize(raw)) == expected
