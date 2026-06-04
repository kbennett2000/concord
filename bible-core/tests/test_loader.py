"""Loader behavior on synthetic fixtures: counts, known verses, chapter_count, FTS5,
idempotency."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import LoaderError, build_database
from loaderkit import book, chapter, translation, verse, write_translation

GEN_1_1 = "In the beginning God created the heaven and the earth."


def _corpus(tmp_path: Path) -> Path:
    """Two translations: Genesis ch.1-2 (3 verses) + John ch.1 (1 verse) each."""
    tdir = tmp_path / "translations"
    kjv = translation(
        "KJVX",
        [
            book(
                "Gen",
                1,
                [
                    chapter(1, [verse(1, GEN_1_1), verse(2, "And the earth was without form.")]),
                    chapter(2, [verse(1, "Thus the heavens were finished.")]),
                ],
            ),
            book("John", 43, [chapter(1, [verse(1, "In the beginning was the Word.")])]),
        ],
    )
    web = translation(
        "WEBX",
        [
            book(
                "Gen",
                1,
                [
                    chapter(1, [verse(1, "In the beginning God created."), verse(2, "The earth.")]),
                    chapter(2, [verse(1, "The heavens were finished.")]),
                ],
            ),
            book("John", 43, [chapter(1, [verse(1, "In the beginning was the Word.")])]),
        ],
    )
    write_translation(tdir, kjv)
    write_translation(tdir, web)
    return tdir


def test_row_counts(tmp_path: Path) -> None:
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    conn = sqlite3.connect(tmp_path / "bible.db")
    assert conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0] == 8  # 2 * (3 + 1)
    assert stats.translations == 2
    assert stats.verses == 8


def test_known_verse_text_matches_source(tmp_path: Path) -> None:
    build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    conn = sqlite3.connect(tmp_path / "bible.db")
    text = conn.execute(
        "SELECT text FROM verses WHERE translation_id='KJVX' AND book_id='GEN' "
        "AND chapter=1 AND verse=1"
    ).fetchone()[0]
    assert text == GEN_1_1


def test_chapter_count_computed(tmp_path: Path) -> None:
    build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    conn = sqlite3.connect(tmp_path / "bible.db")
    assert conn.execute("SELECT chapter_count FROM books WHERE id='GEN'").fetchone()[0] == 2
    assert conn.execute("SELECT chapter_count FROM books WHERE id='JHN'").fetchone()[0] == 1
    # a book with no verses keeps the seeded NULL
    assert conn.execute("SELECT chapter_count FROM books WHERE id='REV'").fetchone()[0] is None


def test_fts_finds_known_phrase(tmp_path: Path) -> None:
    build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    conn = sqlite3.connect(tmp_path / "bible.db")
    hits = conn.execute(
        "SELECT v.book_id, v.chapter, v.verse FROM verses_fts f "
        "JOIN verses v ON v.id = f.rowid "
        "WHERE verses_fts MATCH 'beginning' AND v.translation_id='KJVX'"
    ).fetchall()
    assert ("GEN", 1, 1) in [tuple(h) for h in hits]


def test_build_is_idempotent_hash(tmp_path: Path) -> None:
    tdir = _corpus(tmp_path)
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    build_database(a, [tdir])
    build_database(b, [tdir])
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()


def test_rebuild_same_path_is_clean(tmp_path: Path) -> None:
    tdir = _corpus(tmp_path)
    db = tmp_path / "bible.db"
    build_database(db, [tdir])
    first = db.read_bytes()
    build_database(db, [tdir])  # delete-and-rebuild
    assert db.read_bytes() == first


def test_duplicate_code_is_rejected(tmp_path: Path) -> None:
    tdir = tmp_path / "translations"
    payload = translation("DUP", [book("Gen", 1, [chapter(1, [verse(1, "x")])])])
    write_translation(tdir, payload, filename="one.json")
    write_translation(tdir, payload, filename="two.json")
    with pytest.raises(LoaderError, match="Duplicate translation code"):
        build_database(tmp_path / "bible.db", [tdir])
