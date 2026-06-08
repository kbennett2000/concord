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
from bible_core.parser import parse_reference
from bible_core.queries import get_strongs, get_strongs_verses, get_words_for_reference
from bible_core.resolver import SqliteBookResolver

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"
LEXICON = REPO_ROOT / "data" / "strongs"
TOKENS = REPO_ROOT / "data" / "strongs"


def _consonants(hebrew: str) -> str:
    """Drop Hebrew points/cantillation — compare a word's consonantal skeleton, which is stable
    regardless of how vowels/accents are hand-typed in a test literal."""
    return "".join(c for c in unicodedata.normalize("NFD", hebrew) if not unicodedata.combining(c))


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

    # 15 committed translations: 13 public-domain English + the Greek SBLGNT + the Hebrew OSHB
    # (both CC BY 4.0, STEPBible). data/private is not scanned here.
    assert stats.translations == 15
    assert conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0] == 15
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


def test_real_build_loads_word_tokens_both_directions(tmp_path: Path) -> None:
    """The real SBLGNT tagged tokens load into ``word_tokens`` (v6 S3) and join the lexicon:
    G25 (ἀγαπάω) occurs in John 3:16, and John 3:16's tokens come back in order with glosses."""
    db = tmp_path / "bible.db"
    stats = build_database(db, [TRANSLATIONS], lexicon_dir=LEXICON, tokens_dir=LEXICON)
    assert stats.word_tokens > 130000
    conn = sqlite3.connect(db)

    # Strong's → verses: ἠγάπησεν in John 3:16 is G25 (ἀγαπάω), so John 3:16 is among its verses.
    _, total = get_strongs_verses(conn, "G25", "SBLGNT", 5, 0)
    assert total > 0
    john_316 = conn.execute(
        "SELECT COUNT(*) FROM word_tokens "
        "WHERE strongs_id='G25' AND text_id='SBLGNT' "
        "AND book_id='JHN' AND chapter=3 AND verse=16"
    ).fetchone()[0]
    assert john_316 == 1

    # verse → tokens: John 3:16 returns its SBL words in order, with lemma/gloss joined.
    ref = parse_reference("John 3:16", SqliteBookResolver(conn))
    toks = get_words_for_reference(conn, ref, "SBLGNT")
    assert [t.position for t in toks][:2] == [1, 2]
    assert toks[0].surface_form == unicodedata.normalize("NFC", "οὕτως")
    agapao = next(t for t in toks if t.strongs_id == "G25")
    assert agapao.lemma == unicodedata.normalize("NFC", "ἀγαπάω")
    assert "love" in (agapao.gloss or "")
    # The TR-only αὐτοῦ (#11) is absent from the SBL token stream, like the verse text.
    assert "αὐτοῦ" not in [t.surface_form for t in toks]


def test_real_build_loads_the_hebrew_ot(tmp_path: Path) -> None:
    """The real Hebrew OT (OSHB, from TAHOT) loads as an RTL translation under English/NRSV
    versification (v6 S5): it agrees with the English on chapter counts (no LoaderError), its
    tokens + the Hebrew lexicon (TBESH) join, and word study works for an OT verse."""
    db = tmp_path / "bible.db"
    stats = build_database(db, [TRANSLATIONS], lexicon_dir=LEXICON, tokens_dir=TOKENS)
    conn = sqlite3.connect(db)

    meta = conn.execute(
        "SELECT name, language, direction FROM translations WHERE id='OSHB'"
    ).fetchone()
    assert meta == ("Open Scriptures Hebrew Bible", "hbo", "rtl")
    # English/NRSV versification: Malachi 4 chapters, Joel 3 — matching the English Bibles, which is
    # why the build did not raise on chapter-count disagreement.
    assert stats.translations == 15  # type: ignore[attr-defined]
    for book_id, n in (("MAL", 4), ("JOL", 3)):
        assert (
            conn.execute(
                "SELECT COUNT(DISTINCT chapter) FROM verses "
                "WHERE translation_id='OSHB' AND book_id=?",
                (book_id,),
            ).fetchone()[0]
            == n
        )
    # Genesis 1:1 Hebrew text loads with its pointing/cantillation; its 7 words' consonantal
    # skeleton begins בראשית ברא אלהים … ("In the beginning God created …").
    gen = conn.execute(
        "SELECT text FROM verses WHERE translation_id='OSHB' AND book_id='GEN' "
        "AND chapter=1 AND verse=1"
    ).fetchone()[0]
    assert _consonants(gen).split()[:3] == ["בראשית", "ברא", "אלהים"]

    # Lexicon: H430 = אֱלֹהִים "God" (compare consonants — the lemma carries vowel points).
    elohim = get_strongs(conn, "H430")
    assert elohim is not None
    assert _consonants(elohim.lemma) == "אלהים"
    assert "God" in elohim.gloss
    assert elohim.language == "hbo"

    # Strong's → verses: H430 occurs in Genesis 1:1.
    _, total = get_strongs_verses(conn, "H430", "OSHB", 5, 0)
    assert total > 0
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM word_tokens "
            "WHERE strongs_id='H430' AND text_id='OSHB' AND book_id='GEN' AND chapter=1 AND verse=1"
        ).fetchone()[0]
        == 1
    )

    # verse → tokens: Genesis 1:1's Hebrew words, in order, with the root lemma/gloss joined.
    ref = parse_reference("Genesis 1:1", SqliteBookResolver(conn))
    toks = get_words_for_reference(conn, ref, "OSHB")
    assert len(toks) == 7
    elohim_tok = next(t for t in toks if t.strongs_id == "H430")
    assert _consonants(elohim_tok.lemma or "") == "אלהים"
    assert "God" in (elohim_tok.gloss or "")
