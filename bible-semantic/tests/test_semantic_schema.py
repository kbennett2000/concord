"""The embeddings store schema: tables, columns, idempotency. No model required."""

from __future__ import annotations

import sqlite3

from bible_semantic.schema import (
    EMBEDDING_META_TABLE,
    VERSE_EMBEDDINGS_TABLE,
    create_embeddings_schema,
)


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def test_creates_expected_tables_and_columns() -> None:
    conn = sqlite3.connect(":memory:")
    create_embeddings_schema(conn)

    assert _columns(conn, VERSE_EMBEDDINGS_TABLE) == ["book_id", "chapter", "verse", "vector"]
    assert _columns(conn, EMBEDDING_META_TABLE) == [
        "model",
        "model_revision",
        "dim",
        "precision",
        "translation",
        "normalized",
        "built_at",
    ]


def test_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    create_embeddings_schema(conn)
    create_embeddings_schema(conn)  # second run must not raise
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {VERSE_EMBEDDINGS_TABLE, EMBEDDING_META_TABLE} <= tables
