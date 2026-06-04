"""Integration: SqliteBookResolver against the real seeded alias data.

Excluded from the default run; uses create_schema + seed_books (the actual
canonical-books.md aliases) on a temp DB file, not synthetic fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bible_core.db import connect
from bible_core.resolver import BookInfo, SqliteBookResolver
from bible_core.schema import create_schema
from bible_core.seed import seed_books

pytestmark = pytest.mark.integration


def test_sqlite_resolver_uses_real_aliases(tmp_path: Path) -> None:
    conn = connect(tmp_path / "bible.db")
    create_schema(conn)
    seed_books(conn)
    resolver = SqliteBookResolver(conn)

    assert resolver.resolve("jud") == BookInfo("JUD", "Jude")  # disambiguation
    assert resolver.resolve("jdg") == BookInfo("JDG", "Judges")
    assert resolver.resolve("1 John") == BookInfo("1JN", "1 John")
    assert resolver.resolve("First John") == BookInfo("1JN", "1 John")
    assert resolver.resolve("Genesis") == BookInfo("GEN", "Genesis")
    assert resolver.resolve("Hezekiah") is None
