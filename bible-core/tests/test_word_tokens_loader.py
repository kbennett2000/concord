"""Word-tokens loader behaviour on synthetic fixtures: tokens land, both directions queryable
(Strong's→verses and verse→tokens with the lexicon gloss joined), the composite PK dedups a
repeated position, an unresolved book is skipped + counted, nullable strongs/morph survive,
ordering holds, and rebuilds are idempotent. The lexicon and token files share one directory
(as in `data/strongs/`); the lexicon loader must ignore the `tokens-*.json` file. No dependence
on the real STEPBible data."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bible_core.loader import build_database
from bible_core.parser import parse_reference
from bible_core.queries import (
    count_strongs_verses,
    get_strongs_verses,
    get_words_for_reference,
)
from bible_core.resolver import SqliteBookResolver
from loaderkit import book, chapter, translation, verse, write_translation


def _corpus(tmp_path: Path) -> Path:
    tdir = tmp_path / "translations"
    grk = translation(
        "GRK",
        [
            book("John", 43, [chapter(3, [verse(16, "οὕτως γὰρ ἠγάπησεν")])]),
            book("1 John", 62, [chapter(4, [verse(8, "ἀγάπη"), verse(16, "ἀγάπη")])]),
        ],
        language="grc",
    )
    write_translation(tdir, grk)
    return tdir


def _lexicon() -> dict[str, object]:
    return {
        "source": "STEP Bible (Tyndale House)",
        "entries": [
            {
                "strongs_id": "G25",
                "language": "grc",
                "lemma": "ἀγαπάω",
                "transliteration": "agapaō",
                "gloss": "to love",
                "definition": "to love.",
            },
            {
                "strongs_id": "G26",
                "language": "grc",
                "lemma": "ἀγάπη",
                "transliteration": "agapē",
                "gloss": "love",
                "definition": "love.",
            },
        ],
    }


def _tokens() -> dict[str, object]:
    return {
        "text_id": "GRK",
        "source": "STEP Bible (Tyndale House)",
        "tokens": [
            # John 3:16 — pos1 tagged but no lexicon entry (G2316), pos2 G25 (joins ἀγαπάω),
            # pos2 repeated (PK dedups), pos3 untagged (null strongs + morph).
            {
                "book": "JHN",
                "chapter": 3,
                "verse": 16,
                "position": 1,
                "surface_form": "θεὸς",
                "strongs_id": "G2316",
                "morph_code": "N-NSM",
            },
            {
                "book": "JHN",
                "chapter": 3,
                "verse": 16,
                "position": 2,
                "surface_form": "ἠγάπησεν",
                "strongs_id": "G25",
                "morph_code": "V-AAI-3S",
            },
            {
                "book": "JHN",
                "chapter": 3,
                "verse": 16,
                "position": 2,
                "surface_form": "DUPLICATE",
                "strongs_id": "G25",
                "morph_code": "V-AAI-3S",
            },
            {
                "book": "JHN",
                "chapter": 3,
                "verse": 16,
                "position": 3,
                "surface_form": "γὰρ",
                "strongs_id": None,
                "morph_code": None,
            },
            # G26 in two distinct verses (the Strong's→verses direction).
            {
                "book": "1JN",
                "chapter": 4,
                "verse": 8,
                "position": 1,
                "surface_form": "ἀγάπη",
                "strongs_id": "G26",
                "morph_code": "N-NSF",
            },
            {
                "book": "1JN",
                "chapter": 4,
                "verse": 16,
                "position": 1,
                "surface_form": "ἀγάπη",
                "strongs_id": "G26",
                "morph_code": "N-NSF",
            },
            # unresolved book → skipped + counted.
            {
                "book": "ZZZ",
                "chapter": 1,
                "verse": 1,
                "position": 1,
                "surface_form": "x",
                "strongs_id": "G1",
                "morph_code": "X",
            },
        ],
    }


def _build(tmp_path: Path) -> tuple[Path, object]:
    strongs_dir = tmp_path / "strongs"
    strongs_dir.mkdir(parents=True)
    (strongs_dir / "lexicon.json").write_text(json.dumps(_lexicon()), encoding="utf-8")
    (strongs_dir / "tokens-grk.json").write_text(json.dumps(_tokens()), encoding="utf-8")
    stats = build_database(
        tmp_path / "bible.db",
        [_corpus(tmp_path)],
        lexicon_dir=strongs_dir,
        tokens_dir=strongs_dir,
    )
    return tmp_path / "bible.db", stats


def test_counts_dedup_and_skip(tmp_path: Path) -> None:
    _, stats = _build(tmp_path)
    # 5 distinct PKs (the repeated JHN 3:16 #2 collapses); ZZZ skipped. The lexicon still loads
    # 2 entries even though tokens-grk.json shares the directory.
    assert stats.word_tokens == 5  # type: ignore[attr-defined]
    assert stats.strongs_entries == 2  # type: ignore[attr-defined]


def test_strongs_to_verses_distinct_and_ordered(tmp_path: Path) -> None:
    db, _ = _build(tmp_path)
    conn = sqlite3.connect(db)
    rows, total = get_strongs_verses(conn, "G26", "GRK", 50, 0)
    assert total == 2
    assert [(r.book_id, r.chapter, r.verse) for r in rows] == [("1JN", 4, 8), ("1JN", 4, 16)]
    assert count_strongs_verses(conn, "G26", "GRK") == 2
    # A Strong's not in this text → no verses.
    assert count_strongs_verses(conn, "G26", "NOPE") == 0


def test_verse_to_words_ordered_with_lexicon_join(tmp_path: Path) -> None:
    db, _ = _build(tmp_path)
    conn = sqlite3.connect(db)
    ref = parse_reference("John 3:16", SqliteBookResolver(conn))
    toks = get_words_for_reference(conn, ref, "GRK")
    # Position order; the repeated #2 collapsed (first surface wins, not "DUPLICATE").
    assert [t.position for t in toks] == [1, 2, 3]
    assert [t.surface_form for t in toks] == ["θεὸς", "ἠγάπησεν", "γὰρ"]
    # pos2 G25 joins the lexicon (ἀγαπάω / "to love"); pos1 G2316 has no entry → None.
    assert (toks[1].strongs_id, toks[1].lemma, toks[1].gloss) == ("G25", "ἀγαπάω", "to love")
    assert (toks[0].strongs_id, toks[0].lemma, toks[0].gloss) == ("G2316", None, None)
    # pos3 is untagged: null strongs + morph survive the round-trip.
    assert (toks[2].strongs_id, toks[2].morph_code) == (None, None)


def test_words_for_reference_empty_when_no_tokens(tmp_path: Path) -> None:
    db, _ = _build(tmp_path)
    conn = sqlite3.connect(db)
    # A verse the text doesn't tag (an OT book for this NT-only text) → empty, not an error.
    ref = parse_reference("Genesis 1:1", SqliteBookResolver(conn))
    assert get_words_for_reference(conn, ref, "GRK") == ()


def test_build_is_idempotent(tmp_path: Path) -> None:
    first = _build(tmp_path)[1]
    second = build_database(
        tmp_path / "bible.db",
        [_corpus(tmp_path)],
        lexicon_dir=tmp_path / "strongs",
        tokens_dir=tmp_path / "strongs",
    )
    assert first.word_tokens == second.word_tokens  # type: ignore[attr-defined]


def test_no_tokens_dir_yields_zero(tmp_path: Path) -> None:
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])  # tokens_dir omitted
    assert stats.word_tokens == 0
