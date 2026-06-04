"""DictBookResolver resolves through normalization; unknown tokens return None."""

from __future__ import annotations

from bible_core.resolver import BookInfo
from parserkit import make_resolver

RESOLVER = make_resolver()


def test_resolves_canonical_name() -> None:
    assert RESOLVER.resolve("Genesis") == BookInfo("GEN", "Genesis")


def test_resolves_alias_with_normalization() -> None:
    assert RESOLVER.resolve("I John") == BookInfo("1JN", "1 John")
    assert RESOLVER.resolve("1 Jn.") == BookInfo("1JN", "1 John")
    assert RESOLVER.resolve("SONG OF SOLOMON") == BookInfo("SNG", "Song of Solomon")


def test_unknown_token_returns_none() -> None:
    assert RESOLVER.resolve("Hezekiah") is None
