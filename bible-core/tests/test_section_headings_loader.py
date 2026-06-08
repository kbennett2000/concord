"""Section-headings ingest on synthetic fixtures: the loader bakes `chapters[].headings[]`
(previously discarded) into `section_headings`, ordered, deterministic, idempotent, and a
chapter/translation with none yields zero rows. No dependence on the large real files."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bible_core.loader import build_database
from loaderkit import book, chapter, heading, translation, verse, write_translation


def _corpus(tmp_path: Path) -> Path:
    """Two translations: WEBX carries headings (incl. a chapter with several + a heading-less
    chapter); BSBX carries none (the empty-on-stock case, like the real BSB)."""
    tdir = tmp_path / "translations"
    webx = translation(
        "WEBX",
        [
            book(
                "Gen",
                1,
                [
                    chapter(
                        1,
                        [verse(1, "In the beginning."), verse(2, "Earth."), verse(3, "Light.")],
                        headings=[heading(1, "The Creation"), heading(3, "The First Day")],
                    )
                ],
            ),
            book(
                "John",
                43,
                [
                    chapter(
                        3,
                        [verse(1, "Now there was a man."), verse(2, "He came by night.")],
                        headings=[heading(1, "Jesus and Nicodemus")],
                    ),
                    chapter(4, [verse(1, "Therefore.")]),  # no headings
                ],
            ),
        ],
    )
    # Same chapter skeleton as WEBX (the loader requires translations agree on chapter counts),
    # but carries NO headings — the empty-on-stock case, like the real BSB.
    bsbx = translation(
        "BSBX",
        [
            book("Gen", 1, [chapter(1, [verse(1, "x"), verse(2, "y"), verse(3, "z")])]),
            book(
                "John",
                43,
                [chapter(3, [verse(1, "a"), verse(2, "b")]), chapter(4, [verse(1, "c")])],
            ),
        ],
    )
    write_translation(tdir, webx)
    write_translation(tdir, bsbx)
    return tdir


def test_headings_land_with_anchor_and_order(tmp_path: Path) -> None:
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    assert stats.section_headings == 3  # 2 in GEN 1 + 1 in JHN 3

    conn = sqlite3.connect(tmp_path / "bible.db")
    rows = conn.execute(
        "SELECT before_verse, ordinal, text FROM section_headings "
        "WHERE translation_id='WEBX' AND book_id='GEN' AND chapter=1 "
        "ORDER BY before_verse, ordinal, id"
    ).fetchall()
    assert rows == [(1, 1, "The Creation"), (3, 2, "The First Day")]


def test_known_heading_text(tmp_path: Path) -> None:
    build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    conn = sqlite3.connect(tmp_path / "bible.db")
    text = conn.execute(
        "SELECT text FROM section_headings WHERE translation_id='WEBX' AND book_id='JHN' "
        "AND chapter=3 AND before_verse=1"
    ).fetchone()[0]
    assert text == "Jesus and Nicodemus"


def test_chapter_without_headings_yields_zero(tmp_path: Path) -> None:
    build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    conn = sqlite3.connect(tmp_path / "bible.db")
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM section_headings WHERE book_id='JHN' AND chapter=4"
        ).fetchone()[0]
        == 0
    )


def test_translation_without_headings_yields_zero(tmp_path: Path) -> None:
    build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    conn = sqlite3.connect(tmp_path / "bible.db")
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM section_headings WHERE translation_id='BSBX'"
        ).fetchone()[0]
        == 0
    )


def test_build_is_idempotent(tmp_path: Path) -> None:
    first = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])
    second = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])  # delete-and-rebuild
    assert first.section_headings == second.section_headings == 3


def test_ordinal_preserves_source_order_not_verse_order(tmp_path: Path) -> None:
    """When two headings sit before the SAME verse, source array order is preserved by ordinal."""
    tdir = tmp_path / "translations"
    payload = translation(
        "WEBX",
        [
            book(
                "Gen",
                1,
                [chapter(1, [verse(1, "x")], headings=[heading(1, "First"), heading(1, "Second")])],
            )
        ],
    )
    write_translation(tdir, payload)
    build_database(tmp_path / "bible.db", [tdir])
    conn = sqlite3.connect(tmp_path / "bible.db")
    rows = conn.execute("SELECT ordinal, text FROM section_headings ORDER BY ordinal").fetchall()
    assert rows == [(1, "First"), (2, "Second")]
