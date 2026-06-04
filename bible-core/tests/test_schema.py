"""Schema creation, idempotency, FTS5 availability, and constraint behavior."""

from __future__ import annotations

import sqlite3

import pytest
from bible_core.schema import create_schema

EXPECTED_TABLES = {
    "translations",
    "books",
    "book_aliases",
    "verses",
    "cross_references",
    "verses_fts",
}
EXPECTED_INDEXES = {"idx_verses_bcv", "idx_verses_tbc", "idx_xref_from"}


def _fresh() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    return conn


def _names(conn: sqlite3.Connection, kind: str) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,)).fetchall()
    return {row[0] for row in rows}


def test_create_schema_makes_all_tables_and_indexes() -> None:
    conn = _fresh()
    assert _names(conn, "table") >= EXPECTED_TABLES
    assert _names(conn, "index") >= EXPECTED_INDEXES


def test_create_schema_is_idempotent() -> None:
    conn = _fresh()
    create_schema(conn)  # second run must not raise
    assert _names(conn, "table") >= EXPECTED_TABLES


def test_fts5_is_available_and_functional() -> None:
    # create_schema succeeding already proves FTS5 is compiled in; confirm it queries.
    conn = _fresh()
    conn.execute("INSERT INTO verses_fts(rowid, text) VALUES (1, 'in the beginning')")
    row = conn.execute("SELECT rowid FROM verses_fts WHERE verses_fts MATCH 'beginning'").fetchone()
    assert row[0] == 1


def test_dc_testament_is_permitted() -> None:
    # v1 seeds no DC books, but the schema must allow them (Catholic data, later).
    conn = _fresh()
    conn.execute(
        "INSERT INTO books (id, name, testament, canonical_order) VALUES (?, ?, ?, ?)",
        ("TOB", "Tobit", "DC", 100),
    )
    assert conn.execute("SELECT testament FROM books WHERE id = 'TOB'").fetchone()[0] == "DC"


def test_invalid_testament_is_rejected() -> None:
    conn = _fresh()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO books (id, name, testament, canonical_order) VALUES (?, ?, ?, ?)",
            ("XXX", "Bad", "ZZ", 101),
        )


def test_foreign_keys_are_enforced() -> None:
    conn = _fresh()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO book_aliases (alias, book_id) VALUES (?, ?)",
            ("ghost", "NOPE"),
        )
