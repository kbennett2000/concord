"""An original-language text loads as an ordinary translation (v6 Slice 1, fast/synthetic).

The Greek NT (and later Hebrew OT) reuses the existing translations machinery — it is just
another translation file with a non-English ``language``. This proves the capability on a tiny
synthetic corpus, independent of the real STEPBible data: a Greek translation sits beside an
English one, its verses are stored verbatim and retrievable, its ``language`` is preserved, and
``_update_chapter_counts`` accepts it because the two agree on chapter counts per shared book.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import LoaderError, build_database
from bible_core.queries import get_verse_text
from loaderkit import book, chapter, translation, verse, write_translation


def _corpus(tmp_path: Path) -> Path:
    tdir = tmp_path / "translations"
    english = translation(
        "ENG",
        [book("John", 43, [chapter(3, [verse(16, "For God so loved the world")])])],
    )
    greek = translation(
        "GRK",
        [book("John", 43, [chapter(3, [verse(16, "οὕτως γὰρ ἠγάπησεν ὁ θεὸς τὸν κόσμον")])])],
        name="Greek NT",
        language="grc",
        attribution="CC BY 4.0.",
    )
    write_translation(tdir, english)
    write_translation(tdir, greek)
    return tdir


def test_greek_translation_loads_beside_english(tmp_path: Path) -> None:
    db = tmp_path / "bible.db"
    stats = build_database(db, [_corpus(tmp_path)])
    assert stats.translations == 2

    conn = sqlite3.connect(db)
    # The non-English language is preserved; direction defaults to ltr (Greek is LTR).
    meta = conn.execute("SELECT language, direction FROM translations WHERE id='GRK'").fetchone()
    assert meta == ("grc", "ltr")
    # The Greek verse is stored verbatim and retrievable via the normal query path.
    assert get_verse_text(conn, "GRK", "JHN", 3, 16) == "οὕτως γὰρ ἠγάπησεν ὁ θεὸς τὸν κόσμον"
    assert get_verse_text(conn, "ENG", "JHN", 3, 16) == "For God so loved the world"


def test_hebrew_translation_loads_rtl(tmp_path: Path) -> None:
    """A Hebrew OL text declares ``direction="rtl"`` in its file; the loader reads it and stores it
    (Hebrew is RTL). Verses load verbatim through the normal path (v6 S5)."""
    tdir = tmp_path / "translations"
    write_translation(tdir, translation("ENG", [book("Genesis", 1, [chapter(1, [verse(1, "x")])])]))
    write_translation(
        tdir,
        translation(
            "HEB",
            [book("Genesis", 1, [chapter(1, [verse(1, "בְּרֵאשִׁית")])])],
            language="hbo",
            direction="rtl",
        ),
    )
    db = tmp_path / "bible.db"
    build_database(db, [tdir])
    conn = sqlite3.connect(db)
    meta = conn.execute("SELECT language, direction FROM translations WHERE id='HEB'").fetchone()
    assert meta == ("hbo", "rtl")
    assert get_verse_text(conn, "HEB", "GEN", 1, 1) == "בְּרֵאשִׁית"


def test_direction_defaults_to_ltr_when_absent(tmp_path: Path) -> None:
    """A translation file with no ``direction`` field loads as ltr (the common case)."""
    tdir = tmp_path / "translations"
    write_translation(tdir, translation("ENG", [book("Genesis", 1, [chapter(1, [verse(1, "x")])])]))
    build_database(tmp_path / "bible.db", [tdir])
    conn = sqlite3.connect(tmp_path / "bible.db")
    assert conn.execute("SELECT direction FROM translations WHERE id='ENG'").fetchone()[0] == "ltr"


def test_invalid_direction_rejected(tmp_path: Path) -> None:
    tdir = tmp_path / "translations"
    books = [book("Genesis", 1, [chapter(1, [verse(1, "x")])])]
    write_translation(tdir, translation("ENG", books, direction="sideways"))
    with pytest.raises(LoaderError, match="direction"):
        build_database(tmp_path / "bible.db", [tdir])


def test_chapter_count_agreement_still_enforced(tmp_path: Path) -> None:
    """An OL text that disagrees on chapter count for a shared book is still rejected. (The real
    Hebrew OT avoids this by loading under English/NRSV versification — TAHOT's primary numbering —
    so its chapter counts match the English Bibles; no per-versification relaxation was needed.)"""
    tdir = tmp_path / "translations"
    write_translation(tdir, translation("ENG", [book("John", 43, [chapter(1, [verse(1, "a")])])]))
    write_translation(
        tdir,
        translation(
            "GRK",
            [book("John", 43, [chapter(1, [verse(1, "α")]), chapter(2, [verse(1, "β")])])],
            language="grc",
        ),
    )
    with pytest.raises(LoaderError, match="chapter count"):
        build_database(tmp_path / "bible.db", [tdir])
