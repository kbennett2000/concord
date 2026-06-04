"""Book resolution: a token (``"1 Jn"``, ``"Genesis"``) → canonical USFM id + name.

The parser depends only on the ``BookResolver`` protocol, so it stays pure and DB-free;
callers inject a concrete resolver. The resolver owns normalization (it applies Slice 1's
``normalize()`` before lookup), which is why ``parser.py`` never imports ``normalize``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .normalize import normalize


@dataclass(frozen=True)
class BookInfo:
    """A resolved book: its USFM id and canonical display name."""

    id: str
    name: str


class BookResolver(Protocol):
    """Resolve a raw book token to a :class:`BookInfo`, or ``None`` if unknown."""

    def resolve(self, token: str) -> BookInfo | None: ...


class SqliteBookResolver:
    """Production resolver backed by the seeded ``book_aliases`` / ``books`` tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def resolve(self, token: str) -> BookInfo | None:
        row = self._conn.execute(
            "SELECT b.id, b.name FROM book_aliases a "
            "JOIN books b ON b.id = a.book_id WHERE a.alias = ?",
            (normalize(token),),
        ).fetchone()
        if row is None:
            return None
        return BookInfo(id=row[0], name=row[1])


class DictBookResolver:
    """In-memory resolver (DB-free) keyed by normalized alias. Handy for tests/embedding."""

    def __init__(self, by_alias: dict[str, BookInfo]) -> None:
        self._by_alias = by_alias

    def resolve(self, token: str) -> BookInfo | None:
        return self._by_alias.get(normalize(token))

    @classmethod
    def from_books(cls, books: Iterable[tuple[str, str, Iterable[str]]]) -> DictBookResolver:
        """Build from ``(id, name, aliases)`` rows.

        Each book's normalized name and lowercased id are registered automatically, in
        addition to the supplied aliases — mirroring the seed contract.
        """
        by_alias: dict[str, BookInfo] = {}
        for book_id, name, aliases in books:
            info = BookInfo(id=book_id, name=name)
            keys = {normalize(name), normalize(book_id), *(normalize(a) for a in aliases)}
            for key in keys:
                by_alias[key] = info
        return cls(by_alias)
