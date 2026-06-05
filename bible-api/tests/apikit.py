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

    # Compute chapter_count for populated books, mirroring the loader, so /books returns
    # real values (books without verses keep the seeded NULL).
    conn.execute(
        "UPDATE books SET chapter_count = ("
        "  SELECT COUNT(DISTINCT v.chapter) FROM verses v WHERE v.book_id = books.id"
        ") WHERE id IN (SELECT DISTINCT book_id FROM verses)"
    )

    # Deterministic cross-references for the endpoint tests:
    #  - John 3:16 → 4 targets (votes 50/40/30/5) incl. a same-chapter range (JHN 4:2-4)
    #  - John 4:1  → JHN 3:16, which WEB omits (exercises include_text null)
    # (from_book, from_ch, from_v, to_book, to_ch, to_vstart, to_vend, votes)
    cross_refs = [
        ("JHN", 3, 16, "GEN", 1, 1, None, 50),
        ("JHN", 3, 16, "1JN", 1, 1, None, 40),
        ("JHN", 3, 16, "JHN", 4, 2, 4, 30),  # same-chapter range target
        ("JHN", 3, 16, "JHN", 4, 1, None, 5),  # low votes (min_votes filter)
        ("JHN", 4, 1, "JHN", 3, 16, None, 20),  # target WEB omits
    ]
    conn.executemany(
        "INSERT INTO cross_references "
        "(from_book_id, from_chapter, from_verse, to_book_id, to_chapter, "
        "to_verse_start, to_verse_end, votes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        cross_refs,
    )

    # Deterministic geography for the places endpoints:
    #  - Jerusalem: identified, coords (named lat/lon), linked to JHN 3:16 + GEN 1:1-2
    #  - Nod: unknown, NULL coords/confidence (the honesty model)
    #  - two Antiochs sharing name "Antioch": disambiguation, one disputed
    # (id, friendly_id, name, url_slug, type, article, lat, lon, conf, score, status, modern)
    places = [
        (
            "p_jeru",
            "Jerusalem",
            "Jerusalem",
            "jerusalem",
            "settlement",
            "",
            31.78,
            35.23,
            "high",
            1000,
            "identified",
            "Jerusalem",
        ),
        ("p_nod", "Nod", "Nod", "nod", "region", "", None, None, None, None, "unknown", None),
        (
            "p_ant1",
            "Antioch 1",
            "Antioch",
            "antioch-1",
            "settlement",
            "",
            36.20,
            36.16,
            "high",
            900,
            "identified",
            "Antakya",
        ),
        (
            "p_ant2",
            "Antioch 2",
            "Antioch",
            "antioch-2",
            "settlement",
            "",
            38.30,
            31.18,
            "medium",
            300,
            "disputed",
            "Yalvaç",
        ),
    ]
    place_verses = [
        ("p_jeru", "JHN", 3, 16),  # WEB omits this verse → include_text null path
        ("p_jeru", "GEN", 1, 1),
        ("p_jeru", "GEN", 1, 2),
        ("p_nod", "JHN", 4, 1),
        ("p_ant1", "1JN", 1, 1),
        ("p_ant2", "1JN", 1, 2),
    ]
    conn.executemany(
        "INSERT INTO places (id, friendly_id, name, url_slug, type, preceding_article, "
        "latitude, longitude, confidence, confidence_score, status, modern_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        places,
    )
    conn.executemany(
        "INSERT INTO place_verses (place_id, book_id, chapter, verse) VALUES (?, ?, ?, ?)",
        place_verses,
    )
    conn.commit()
    conn.close()
