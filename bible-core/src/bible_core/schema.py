"""SQLite schema for Concord (SPEC §4).

All six tables are created as one cohesive unit even though most stay empty until later
slices — this locks the schema shape early so future slices don't drift it. The schema
carries its future-proofing now: ``translations.versification`` / ``direction``, a
``DC`` testament value (reserved for Catholic data; unused in the v1 seed), and the
``verses`` surrogate ``INTEGER PRIMARY KEY`` that lets the FTS5 index use external
content. ``create_schema`` is idempotent (every statement is ``IF NOT EXISTS``).
"""

from __future__ import annotations

import sqlite3

# Ordinary tables and indexes. Order matters: referenced tables (books, translations)
# come before the tables whose foreign keys point at them.
_TABLES: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS translations (
        id            TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        language      TEXT NOT NULL,
        direction     TEXT NOT NULL DEFAULT 'ltr' CHECK (direction IN ('ltr', 'rtl')),
        versification TEXT NOT NULL,
        attribution   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS books (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        testament       TEXT NOT NULL CHECK (testament IN ('OT', 'NT', 'DC')),
        canonical_order INTEGER NOT NULL UNIQUE,
        chapter_count   INTEGER
    )
    """,
    # alias is the PRIMARY KEY, so "no alias maps to two books" is enforced by the DB
    # as well as by seed-time validation.
    """
    CREATE TABLE IF NOT EXISTS book_aliases (
        alias   TEXT PRIMARY KEY,
        book_id TEXT NOT NULL REFERENCES books (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verses (
        id             INTEGER PRIMARY KEY,
        translation_id TEXT NOT NULL REFERENCES translations (id),
        book_id        TEXT NOT NULL REFERENCES books (id),
        chapter        INTEGER NOT NULL,
        verse          INTEGER NOT NULL,
        text           TEXT NOT NULL,
        UNIQUE (translation_id, book_id, chapter, verse)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cross_references (
        id             INTEGER PRIMARY KEY,
        from_book_id   TEXT NOT NULL REFERENCES books (id),
        from_chapter   INTEGER NOT NULL,
        from_verse     INTEGER NOT NULL,
        to_book_id     TEXT NOT NULL REFERENCES books (id),
        to_chapter     INTEGER NOT NULL,
        to_verse_start INTEGER NOT NULL,
        to_verse_end   INTEGER,
        votes          INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_verses_bcv ON verses (book_id, chapter, verse)",
    "CREATE INDEX IF NOT EXISTS idx_verses_tbc ON verses (translation_id, book_id, chapter)",
    "CREATE INDEX IF NOT EXISTS idx_xref_from "
    "ON cross_references (from_book_id, from_chapter, from_verse)",
)

# FTS5 virtual table over verse text, external-content linked to verses.id.
_FTS = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts "
    "USING fts5(text, content='verses', content_rowid='id')"
)


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables, indexes, and the FTS5 table on ``conn``. Idempotent.

    Enables foreign-key enforcement on this connection (SQLite defaults it off, and the
    pragma is per-connection). Raises a clear ``RuntimeError`` if the runtime SQLite
    build lacks FTS5 — surfacing SPEC §8's "FTS5 compiled in" requirement here, cheaply,
    instead of deep in the Slice 2 loader.
    """
    conn.execute("PRAGMA foreign_keys = ON")
    for statement in _TABLES:
        conn.execute(statement)
    try:
        conn.execute(_FTS)
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "SQLite FTS5 is required but not available in this build. "
            "Concord's search index (verses_fts) cannot be created. "
            "Install or rebuild SQLite with the FTS5 extension enabled."
        ) from exc
    conn.commit()
