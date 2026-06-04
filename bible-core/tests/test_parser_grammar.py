"""One test per supported SPEC §5 grammar form."""

from __future__ import annotations

from bible_core.parser import Span, parse_reference
from parserkit import make_resolver

RESOLVER = make_resolver()


def test_single_verse() -> None:
    ref = parse_reference("John 3:16", RESOLVER)
    assert ref.book_id == "JHN"
    assert ref.book_name == "John"
    assert ref.spans == (Span(3, 16, 3, 16),)
    assert ref.echo == "John 3:16"


def test_verse_range() -> None:
    ref = parse_reference("John 3:16-18", RESOLVER)
    assert ref.spans == (Span(3, 16, 3, 18),)
    assert ref.echo == "John 3:16-18"


def test_verse_list() -> None:
    ref = parse_reference("John 3:16,18,20", RESOLVER)
    assert ref.spans == (Span(3, 16, 3, 16), Span(3, 18, 3, 18), Span(3, 20, 3, 20))
    assert ref.echo == "John 3:16,18,20"


def test_whole_chapter() -> None:
    ref = parse_reference("John 3", RESOLVER)
    assert ref.spans == (Span(3, None, 3, None),)
    assert ref.echo == "John 3"


def test_chapter_range() -> None:
    ref = parse_reference("John 3-4", RESOLVER)
    assert ref.spans == (Span(3, None, 4, None),)
    assert ref.echo == "John 3-4"


def test_cross_chapter_verse_range() -> None:
    ref = parse_reference("John 3:16-4:2", RESOLVER)
    assert ref.spans == (Span(3, 16, 4, 2),)
    assert ref.echo == "John 3:16-4:2"


def test_period_separator_equals_colon() -> None:
    assert parse_reference("John 3.16", RESOLVER) == parse_reference("John 3:16", RESOLVER)


def test_numbered_book() -> None:
    ref = parse_reference("1 John 1:1", RESOLVER)
    assert ref.book_id == "1JN"
    assert ref.echo == "1 John 1:1"


def test_multiword_book() -> None:
    ref = parse_reference("Song of Solomon 1:1", RESOLVER)
    assert ref.book_id == "SNG"
    assert ref.echo == "Song of Solomon 1:1"
