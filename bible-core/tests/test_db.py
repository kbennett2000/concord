"""The connection helper enables foreign keys and name-based row access."""

from __future__ import annotations

from bible_core.db import connect


def test_connect_enables_foreign_keys() -> None:
    conn = connect(":memory:")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connect_uses_row_factory() -> None:
    conn = connect(":memory:")
    conn.execute("CREATE TABLE t (a, b)")
    conn.execute("INSERT INTO t VALUES (1, 2)")
    row = conn.execute("SELECT a, b FROM t").fetchone()
    assert row["a"] == 1
    assert row["b"] == 2
