"""Integration: build from the real committed PD translations and check reality.

Excluded from the default run (``-m "not integration"``); run with ``pytest -m integration``.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from pathlib import Path

import pytest
from bible_core.loader import build_database
from bible_core.queries import get_strongs

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"
LEXICON = REPO_ROOT / "data" / "strongs"


def _source_verse(path: Path, abbreviation: str, ch: int, vs: int) -> str | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for b in data["books"]:
        if b["abbreviation"] == abbreviation:
            for c in b["chapters"]:
                if c["number"] == ch:
                    for v in c["verses"]:
                        if v["number"] == vs:
                            text: str = v["text"]
                            return text.strip()
    return None


def test_real_build_matches_source(tmp_path: Path) -> None:
    db = tmp_path / "bible.db"
    stats = build_database(db, [TRANSLATIONS])
    conn = sqlite3.connect(db)

    # 14 committed translations: 13 public-domain English + the Greek SBLGNT (CC BY 4.0,
    # STEPBible). data/private is not scanned here.
    assert stats.translations == 14
    assert conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0] == 14
    books_with_chapters = conn.execute(
        "SELECT COUNT(*) FROM books WHERE chapter_count IS NOT NULL"
    ).fetchone()[0]
    assert books_with_chapters == 66

    kjv = TRANSLATIONS / "KJV.json"
    for abbreviation, book_id, ch, vs in [
        ("Gen", "GEN", 1, 1),
        ("John", "JHN", 3, 16),
        ("Rev", "REV", 22, 21),
    ]:
        expected = _source_verse(kjv, abbreviation, ch, vs)
        got = conn.execute(
            "SELECT text FROM verses WHERE translation_id='KJV' AND book_id=? "
            "AND chapter=? AND verse=?",
            (book_id, ch, vs),
        ).fetchone()[0]
        assert got == expected


def test_real_build_loads_greek_nt_as_a_translation(tmp_path: Path) -> None:
    """The Greek NT (SBLGNT) loads through the ordinary translations machinery (v6 S1): a Greek,
    NT-only text living beside the English Bibles, its NRSV chapter counts agreeing with theirs.
    """
    db = tmp_path / "bible.db"
    build_database(db, [TRANSLATIONS])
    conn = sqlite3.connect(db)

    meta = conn.execute(
        "SELECT name, language, direction FROM translations WHERE id='SBLGNT'"
    ).fetchone()
    assert meta == ("SBL Greek New Testament", "grc", "ltr")

    # NT-only: it contributes no OT verses, and its chapter counts match the English NT
    # (so _update_chapter_counts did not reject it).
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM verses v JOIN books b ON v.book_id=b.id "
            "WHERE v.translation_id='SBLGNT' AND b.testament='OT'"
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute(
            "SELECT COUNT(DISTINCT chapter) FROM verses "
            "WHERE translation_id='SBLGNT' AND book_id='JHN'"
        ).fetchone()[0]
        == 21
    )

    jhn_316 = conn.execute(
        "SELECT text FROM verses WHERE translation_id='SBLGNT' AND book_id='JHN' "
        "AND chapter=3 AND verse=16"
    ).fetchone()[0]
    # The text is NFC-normalized (the conventional canonical form for a Greek text API).
    assert jhn_316 == unicodedata.normalize("NFC", jhn_316)
    assert jhn_316.startswith(unicodedata.normalize("NFC", "οὕτως γὰρ ἠγάπησεν ὁ θεὸς τὸν κόσμον"))
    # SBL drops the Textus-Receptus-only αὐτοῦ ("his" Son) — proof the SBL-edition filter ran.
    assert "αὐτοῦ" not in jhn_316.split()
    # The whole TR/Byz-only verse John 5:4 is absent from the SBL edition.
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM verses WHERE translation_id='SBLGNT' AND book_id='JHN' "
            "AND chapter=5 AND verse=4"
        ).fetchone()[0]
        == 0
    )


def test_real_build_loads_the_strongs_lexicon(tmp_path: Path) -> None:
    """The real STEPBible Greek lexicon (TBESG) loads into ``strongs_entries`` (v6 S2): the
    canonical G26 entry is ἀγάπη, glossed 'love'."""
    db = tmp_path / "bible.db"
    stats = build_database(db, [TRANSLATIONS], lexicon_dir=LEXICON)
    assert stats.strongs_entries > 10000
    conn = sqlite3.connect(db)
    entry = get_strongs(conn, "G26")
    assert entry is not None
    assert entry.lemma == unicodedata.normalize("NFC", "ἀγάπη")
    assert entry.transliteration == "agapē"
    assert "love" in entry.gloss
    assert entry.language == "grc"
    assert "STEPBible" in entry.source or "STEP Bible" in entry.source
