"""Connection helper.

Foreign-key enforcement in SQLite is off by default and is *per-connection*, so every
connection Concord opens must enable it (deferred here from Slice 1, now that the loader
opens connections to a real database file). Also sets a ``sqlite3.Row`` factory for
name-based column access.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Pragmas that make the bulk load fast. Safe because the database is a throwaway build
# artifact, rebuilt from scratch every run and opened read-only afterward. All three are
# per-connection / non-persisted, so they never affect the output file's bytes.
_LOAD_PRAGMAS = (
    "PRAGMA journal_mode = MEMORY",
    "PRAGMA synchronous = OFF",
    "PRAGMA temp_store = MEMORY",
)


def connect(database: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled and row access by name."""
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_load_pragmas(conn: sqlite3.Connection) -> None:
    """Enable bulk-load performance pragmas on ``conn`` (loader use only)."""
    for pragma in _LOAD_PRAGMAS:
        conn.execute(pragma)


def connect_readonly(database: str | Path) -> sqlite3.Connection:
    """Open a read-only connection to an existing database (URI ``mode=ro``).

    Used by the API: the corpus is immutable, so reads never mutate. Fails if the file
    does not exist, which is the desired fail-fast behavior. ``Row`` factory for
    name-based access.
    """
    conn = sqlite3.connect(f"file:{Path(database)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
