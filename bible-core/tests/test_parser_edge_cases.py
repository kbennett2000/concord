"""The documented edge-case policy — one assertion per row of the policy table."""

from __future__ import annotations

import pytest
from bible_core.parser import ParseError, Span, parse_reference
from parserkit import make_resolver

RESOLVER = make_resolver()

ACCEPTS: list[tuple[str, tuple[Span, ...]]] = [
    # same-bound ranges collapse
    ("John 3-3", (Span(3, None, 3, None),)),
    ("John 3:16-3:16", (Span(3, 16, 3, 16),)),
    ("John 3:16-3:18", (Span(3, 16, 3, 18),)),  # cross-form, same chapter → collapse
    # unicode dashes normalize to ASCII '-'
    ("John 3:16–18", (Span(3, 16, 3, 18),)),  # en dash
    ("John 3:16—18", (Span(3, 16, 3, 18),)),  # em dash
    # no bounds checking on the numbers
    ("John 1:99999999", (Span(1, 99999999, 1, 99999999),)),
    # trailing punctuation on the book is stripped
    ("Jn. 3:16", (Span(3, 16, 3, 16),)),
    # '.' ≡ ':' even when mixed → cross-chapter range
    ("John 3:16-18.20", (Span(3, 16, 18, 20),)),
    # verse lists are sorted and de-duplicated
    ("John 3:18,16", (Span(3, 16, 3, 16), Span(3, 18, 3, 18))),
    ("John 3:16,16", (Span(3, 16, 3, 16),)),
    # whitespace inside the spec is tolerated
    ("John 3 : 16", (Span(3, 16, 3, 16),)),
    ("John 3:16, 18", (Span(3, 16, 3, 16), Span(3, 18, 3, 18))),
    # chapter → chapter:verse: the omitted left verse is the constant 1 (#73, ADR-0010)
    ("John 3-4:2", (Span(3, 1, 4, 2),)),
    ("John 3-4.2", (Span(3, 1, 4, 2),)),  # '.' ≡ ':' reaches the same branch
    ("John 3–4:2", (Span(3, 1, 4, 2),)),  # en dash, folded before dispatch
    ("John 3-3:5", (Span(3, 1, 3, 5),)),  # c1 == c2, already canonical (no collapse needed)
    ("John 3-3:1", (Span(3, 1, 3, 1),)),  # degenerate: one verse
    ("John 03-04:02", (Span(3, 1, 4, 2),)),  # leading zeros (pins the .isdigit() reading)
    ("John 1-99999999:1", (Span(1, 1, 99999999, 1),)),  # no bounds check, still one span
]

REJECTS: list[tuple[str, str]] = [
    ("John 3:18-16", "descending verse range"),
    ("John 5-3", "descending chapter range"),
    ("John 3:16-4", "descending verse range"),
    # the chapter → chapter:verse branch's own boundaries (#73)
    ("John 4-3:2", "descending range"),  # distinct from "descending chapter range"
    ("John 0-4:2", "chapter number must be positive"),
    ("John 3-4:0", "verse number must be positive"),
    ("John 3-4:2:5", "not a valid chapter:verse"),
    # a comma anywhere wins the dispatch, so the new form is still not allowed in a list
    ("John 3-4:2,6", "expected a chapter number"),
    ("John 3:16,4:2", "bare verse numbers"),
    ("John 3:16-18,20", "expected a verse number"),
    ("John", "needs at least a chapter"),
    ("3:16", "no book name found"),
    ("", "empty reference"),
    ("    ", "empty reference"),
    ("John 0:5", "chapter number must be positive"),
    ("John 3:0", "verse number must be positive"),
    ("John -3:16", "missing a bound"),
    ("John 3:16,,18", "empty list element"),
    ("John 3:16--18", "malformed range"),
    ("John 3:16!", "unexpected character"),
    ("Hezekiah 1:1", "unrecognised book"),
    ("John 3:16; Rom 8:1", "multiple references"),
]


@pytest.mark.parametrize(("text", "spans"), ACCEPTS)
def test_accepts(text: str, spans: tuple[Span, ...]) -> None:
    assert parse_reference(text, RESOLVER).spans == spans


@pytest.mark.parametrize(("text", "message"), REJECTS)
def test_rejects(text: str, message: str) -> None:
    with pytest.raises(ParseError, match=message):
        parse_reference(text, RESOLVER)


def test_rejects_oversized_verse_list() -> None:
    # 101 elements: each list element becomes its own SQL query downstream
    # (queries._collect), so the element count is capped to bound the fan-out.
    ref = "John 3:1" + ",1" * 100
    with pytest.raises(ParseError, match="at most 100 are allowed"):
        parse_reference(ref, RESOLVER)


def test_accepts_verse_list_at_cap() -> None:
    # Exactly at the cap (100 elements) still parses.
    ref = "John 3:1" + ",1" * 99
    parse_reference(ref, RESOLVER)  # does not raise
