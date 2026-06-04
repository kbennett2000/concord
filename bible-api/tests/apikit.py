"""Builds the synthetic corpus the API tests run against.

Deterministic verse text (``"JHN 3:16 (KJV)"``) lets tests assert exact strings. WEB
deliberately omits John 3:16 so the missing-verse null path is exercised (the production
corpus has it everywhere — see Slice 2/3 notes).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from bible_core.schema import create_schema
from bible_core.seed import seed_books

TRANSLATIONS = [
    ("KJV", "King James Version"),
    ("WEB", "World English Bible"),
    ("YLT", "Young's Literal Translation"),
]

# (translation_id, book_id, chapter, verse) tuples intentionally absent.
OMITTED = {("WEB", "JHN", 3, 16)}


def verse_text(book_id: str, chapter: int, verse: int, translation_id: str) -> str:
    return f"{book_id} {chapter}:{verse} ({translation_id})"


def build_corpus(path: Path) -> None:
    conn = sqlite3.connect(path)
    create_schema(conn)
    seed_books(conn)
    for translation_id, name in TRANSLATIONS:
        conn.execute(
            "INSERT INTO translations (id, name, language, direction, versification, attribution) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (translation_id, name, "en", "ltr", "standard", "Public domain."),
        )

    rows: list[tuple[str, str, int, int, str]] = []

    def add(book_id: str, chapter: int, verses: Iterable[int]) -> None:
        for translation_id, _ in TRANSLATIONS:
            for verse in verses:
                if (translation_id, book_id, chapter, verse) in OMITTED:
                    continue
                rows.append(
                    (
                        translation_id,
                        book_id,
                        chapter,
                        verse,
                        verse_text(book_id, chapter, verse, translation_id),
                    )
                )

    add("JHN", 3, range(1, 21))  # John 3:1-20 (WEB omits 3:16)
    add("JHN", 4, range(1, 11))  # John 4:1-10
    add("GEN", 1, range(1, 4))  # Genesis 1:1-3
    add("1JN", 1, range(1, 4))  # 1 John 1:1-3

    conn.executemany(
        "INSERT INTO verses (translation_id, book_id, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
