"""iter_verses: read-only bulk reader, canonical order, translation-scoped."""

from __future__ import annotations

import sqlite3

from bible_core.queries import VerseRow, iter_verses
from bible_core.schema import create_schema
from bible_core.seed import seed_books


def _build() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    seed_books(conn)
    for tid in ("WEB", "KJV"):
        conn.execute(
            "INSERT INTO translations (id, name, language, direction, versification, attribution) "
            "VALUES (?, ?, 'en', 'ltr', 'standard', 'PD')",
            (tid, tid),
        )
    # Insert deliberately out of canonical order (JHN before GEN, verses shuffled) to prove
    # iter_verses sorts by book canonical_order then chapter, verse.
    conn.executemany(
        "INSERT INTO verses (translation_id, book_id, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
        [
            ("WEB", "JHN", 3, 16, "WEB JHN 3:16"),
            ("WEB", "JHN", 1, 2, "WEB JHN 1:2"),
            ("WEB", "JHN", 1, 1, "WEB JHN 1:1"),
            ("WEB", "GEN", 1, 2, "WEB GEN 1:2"),
            ("WEB", "GEN", 1, 1, "WEB GEN 1:1"),
            ("KJV", "GEN", 1, 1, "KJV GEN 1:1"),  # other translation — must be excluded
        ],
    )
    conn.commit()
    return conn


def test_yields_only_target_translation_in_canonical_order() -> None:
    conn = _build()
    rows = list(iter_verses(conn, "WEB"))

    assert all(isinstance(r, VerseRow) for r in rows)
    assert all(r.translation_id == "WEB" for r in rows)  # KJV row excluded
    # Genesis (canonical_order 1) before John (43); within a book, by chapter then verse.
    assert [(r.book_id, r.chapter, r.verse) for r in rows] == [
        ("GEN", 1, 1),
        ("GEN", 1, 2),
        ("JHN", 1, 1),
        ("JHN", 1, 2),
        ("JHN", 3, 16),
    ]
    assert rows[0].text == "WEB GEN 1:1"


def test_unknown_translation_yields_nothing() -> None:
    conn = _build()
    assert list(iter_verses(conn, "NOPE")) == []
