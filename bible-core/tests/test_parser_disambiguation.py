"""Parser-level disambiguation and numbered-book equivalence."""

from __future__ import annotations

import pytest
from bible_core.parser import parse_reference
from parserkit import make_resolver

RESOLVER = make_resolver()


def test_jud_is_jude_not_judges() -> None:
    ref = parse_reference("jud 5", RESOLVER)
    assert ref.book_id == "JUD"
    assert ref.echo == "Jude 5"


def test_jdg_is_judges_not_jude() -> None:
    ref = parse_reference("jdg 5", RESOLVER)
    assert ref.book_id == "JDG"
    assert ref.echo == "Judges 5"


@pytest.mark.parametrize(
    "form",
    ["1 John 1:1", "1John 1:1", "1 Jn 1:1", "I John 1:1", "First John 1:1", "1jn 1:1"],
)
def test_numbered_book_forms_parse_identically(form: str) -> None:
    ref = parse_reference(form, RESOLVER)
    assert ref == parse_reference("1 John 1:1", RESOLVER)
    assert ref.echo == "1 John 1:1"
