"""SQLite schema for the semantic embeddings store (docs/v2/SPEC.md §6).

A small database, ``embeddings.db``, owned by ``bible-semantic`` and kept separate from
``bible.db`` so v1's core is untouched. Defined once here so the build side (``build.py``)
and the read side (``store.py``, S2) share a single definition. Like ``bible.db``,
``embeddings.db`` is a build artifact — gitignored, never committed.
"""

from __future__ import annotations

import sqlite3

VERSE_EMBEDDINGS_TABLE = "verse_embeddings"
EMBEDDING_META_TABLE = "embedding_meta"

_TABLES: tuple[str, ...] = (
    # One row per embedded verse. vector = raw float32 bytes (768 x 4 = 3072 bytes).
    """
    CREATE TABLE IF NOT EXISTS verse_embeddings (
        book_id TEXT    NOT NULL,
        chapter INTEGER NOT NULL,
        verse   INTEGER NOT NULL,
        vector  BLOB    NOT NULL,
        PRIMARY KEY (book_id, chapter, verse)
    )
    """,
    # Single guard row — lets the read side refuse vectors built by a different model,
    # revision, or dimension rather than returning garbage similarities.
    """
    CREATE TABLE IF NOT EXISTS embedding_meta (
        model          TEXT    NOT NULL,
        model_revision TEXT    NOT NULL,
        dim            INTEGER NOT NULL,
        translation    TEXT    NOT NULL,
        normalized     INTEGER NOT NULL,
        built_at       TEXT    NOT NULL
    )
    """,
)


def create_embeddings_schema(conn: sqlite3.Connection) -> None:
    """Create the ``verse_embeddings`` + ``embedding_meta`` tables on ``conn``. Idempotent."""
    for statement in _TABLES:
        conn.execute(statement)
    conn.commit()
