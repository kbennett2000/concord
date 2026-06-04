"""The load-bearing invariant: parse(echo(parse(x))) == parse(x) for every form."""

from __future__ import annotations

import pytest
from bible_core.parser import parse_reference
from parserkit import make_resolver

RESOLVER = make_resolver()

SUPPORTED = [
    "John 3:16",
    "John 3:16-18",
    "John 3:16,18,20",
    "John 3",
    "John 3-4",
    "John 3:16-4:2",
    "1 John 1:1",
    "Song of Solomon 1:1",
    "Genesis 1:1-2:3",
    "John 1:99999999",
    # forms whose echo differs from the input still round-trip from their echo
    "John 3.16",
    "John 3-3",
    "John 3:16-3:18",
    "John 3:18,16",
]


@pytest.mark.parametrize("text", SUPPORTED)
def test_echo_reparses_to_same_reference(text: str) -> None:
    once = parse_reference(text, RESOLVER)
    twice = parse_reference(once.echo, RESOLVER)
    assert twice == once


@pytest.mark.parametrize("text", SUPPORTED)
def test_echo_is_idempotent(text: str) -> None:
    once = parse_reference(text, RESOLVER)
    assert parse_reference(once.echo, RESOLVER).echo == once.echo
