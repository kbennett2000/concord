"""SQLite schema for Concord (SPEC §4).

All tables are created as one cohesive unit even though most stay empty until later
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
    # Geography (v3, additive). `id` is OpenBible's ancient id ('a…') — the stable,
    # external-safe PK (SPEC v3 §1). Coordinates / confidence are NULL for places with no
    # confident location (unknown / symbolic / multiple) — the honesty model (v3 §6).
    # `confidence` (evidence strength) and `status` (resolution kind) are independent axes.
    """
    CREATE TABLE IF NOT EXISTS places (
        id                TEXT PRIMARY KEY,
        friendly_id       TEXT NOT NULL,
        name              TEXT NOT NULL,
        url_slug          TEXT NOT NULL,
        type              TEXT NOT NULL,
        preceding_article TEXT NOT NULL DEFAULT '',
        latitude          REAL,
        longitude         REAL,
        confidence        TEXT CHECK (confidence IN ('high', 'medium', 'low')),
        confidence_score  INTEGER,
        status            TEXT NOT NULL CHECK (
            status IN ('identified', 'disputed', 'unknown', 'symbolic', 'multiple')
        ),
        modern_name       TEXT
    )
    """,
    # One row per (place, verse). The composite PK dedups verse links for free and serves
    # BOTH directions: place→verses (WHERE place_id = ?) and verse→places (the index below),
    # exactly as cross_references serves both directions.
    """
    CREATE TABLE IF NOT EXISTS place_verses (
        place_id TEXT NOT NULL REFERENCES places (id),
        book_id  TEXT NOT NULL REFERENCES books (id),
        chapter  INTEGER NOT NULL,
        verse    INTEGER NOT NULL,
        PRIMARY KEY (place_id, book_id, chapter, verse)
    )
    """,
    # Translator's notes (v4, additive). A note is anchored to a verse by CANONICAL
    # coordinates (book_id + chapter + verse) plus `translation_id` — notes are
    # translation-specific because `char_offset` indexes into THAT translation's verse text.
    # This mirrors how `cross_references` / `place_verses` anchor (no `verses.id` FK). The
    # anchor is a single point (`char_offset`), not a span (SPEC v4 §4). `note_type` is a
    # constrained set; NULL is allowed for a plain footnote. Notes are user-supplied from
    # `data/private/` and never ship in the public image (SPEC v4 §2).
    """
    CREATE TABLE IF NOT EXISTS translator_notes (
        id             INTEGER PRIMARY KEY,
        translation_id TEXT NOT NULL REFERENCES translations (id),
        book_id        TEXT NOT NULL REFERENCES books (id),
        chapter        INTEGER NOT NULL,
        verse          INTEGER NOT NULL,
        note_type      TEXT CHECK (note_type IN ('tn', 'sn', 'tc', 'map', 'other')),
        text           TEXT NOT NULL,
        char_offset    INTEGER NOT NULL DEFAULT 0,
        marker         TEXT,
        ordinal        INTEGER NOT NULL
    )
    """,
    # A note's own cross-references → target canonical coords (range via to_verse_end, NULL
    # = single verse). Distinct from `cross_references`, which is verse→verse (TSK); these
    # belong to a `translator_notes` row.
    """
    CREATE TABLE IF NOT EXISTS note_cross_references (
        id             INTEGER PRIMARY KEY,
        note_id        INTEGER NOT NULL REFERENCES translator_notes (id),
        to_book_id     TEXT NOT NULL REFERENCES books (id),
        to_chapter     INTEGER NOT NULL,
        to_verse_start INTEGER NOT NULL,
        to_verse_end   INTEGER
    )
    """,
    # Section headings (additive). A heading anchors a CHAPTER position — it renders BEFORE
    # `before_verse` — keyed by `translation_id` because headings are translation-specific
    # (editorial choices differ per translation; one translation may carry none, e.g. BSB).
    # `ordinal` preserves source array order when a chapter has several. The data already
    # lives in the translation JSON (`chapters[].headings[]`); the loader bakes it here.
    """
    CREATE TABLE IF NOT EXISTS section_headings (
        id             INTEGER PRIMARY KEY,
        translation_id TEXT NOT NULL REFERENCES translations (id),
        book_id        TEXT NOT NULL REFERENCES books (id),
        chapter        INTEGER NOT NULL,
        before_verse   INTEGER NOT NULL,
        text           TEXT NOT NULL,
        ordinal        INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_verses_bcv ON verses (book_id, chapter, verse)",
    "CREATE INDEX IF NOT EXISTS idx_verses_tbc ON verses (translation_id, book_id, chapter)",
    "CREATE INDEX IF NOT EXISTS idx_xref_from "
    "ON cross_references (from_book_id, from_chapter, from_verse)",
    # Supports the verse→places direction (mirrors idx_xref_from).
    "CREATE INDEX IF NOT EXISTS idx_place_verses_bcv ON place_verses (book_id, chapter, verse)",
    # "all notes for this verse/chapter in this translation" — the Slice-2 read lookup.
    "CREATE INDEX IF NOT EXISTS idx_notes_anchor "
    "ON translator_notes (translation_id, book_id, chapter, verse)",
    # A note's cross-references.
    "CREATE INDEX IF NOT EXISTS idx_note_xref_note ON note_cross_references (note_id)",
    # "all headings for this chapter in this translation" — the chapter-read lookup.
    "CREATE INDEX IF NOT EXISTS idx_headings_anchor "
    "ON section_headings (translation_id, book_id, chapter)",
)

# FTS5 virtual tables, external-content linked to their content table's INTEGER PK.
# `verses_fts` over verse text; `notes_fts` over translator-note bodies (v4). Both follow
# the same external-content pattern: the loader rebuilds each after bulk insert. Search-time
# filtering (by translation / note_type) JOINs `notes_fts.rowid = translator_notes.id`.
_FTS: tuple[str, ...] = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts "
    "USING fts5(text, content='verses', content_rowid='id')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts "
    "USING fts5(text, content='translator_notes', content_rowid='id')",
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
        for fts in _FTS:
            conn.execute(fts)
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "SQLite FTS5 is required but not available in this build. "
            "Concord's search indexes (verses_fts, notes_fts) cannot be created. "
            "Install or rebuild SQLite with the FTS5 extension enabled."
        ) from exc
    conn.commit()
