"""Strong's-lexicon loader behaviour on synthetic fixtures: entries land, browse/detail queries
work, the ``q``/``language`` filters and numeric ordering hold, a duplicate id is rejected, an
empty transliteration is allowed, and rebuilds are idempotent. No dependence on the real TBESG
dataset (a real-build assertion lives in ``test_loader_real.py``)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import LoaderError, build_database
from bible_core.queries import get_strongs, list_strongs
from loaderkit import book, chapter, translation, verse, write_translation


def _corpus(tmp_path: Path) -> Path:
    tdir = tmp_path / "translations"
    write_translation(
        tdir,
        translation("WEBX", [book("John", 43, [chapter(3, [verse(16, "For God so loved.")])])]),
    )
    return tdir


def _entries() -> list[dict[str, str]]:
    return [
        {
            "strongs_id": "G26",
            "language": "grc",
            "lemma": "ἀγάπη",
            "transliteration": "agapē",
            "gloss": "love",
            "definition": "love, goodwill, esteem.",
        },
        {
            "strongs_id": "G25",
            "language": "grc",
            "lemma": "ἀγαπάω",
            "transliteration": "agapaō",
            "gloss": "to love",
            "definition": "to love, to feel and exhibit esteem.",
        },
        {
            "strongs_id": "H430",
            "language": "hbo",
            "lemma": "אֱלֹהִים",
            "transliteration": "ʾelōhîm",
            "gloss": "God",
            "definition": "God, gods, rulers.",
        },
        {
            # an extended entry with no transliteration — allowed (stays "")
            "strongs_id": "G21371",
            "language": "grc",
            "lemma": "ἄβρωτος",
            "transliteration": "",
            "gloss": "inedible",
            "definition": "not eaten, inedible.",
        },
    ]


def _lexicon_payload() -> dict[str, object]:
    return {"source": "STEP Bible (Tyndale House)", "entries": _entries()}


def _build(tmp_path: Path, payload: dict[str, object]) -> tuple[Path, object]:
    lexicon_dir = tmp_path / "strongs"
    lexicon_dir.mkdir(parents=True)
    (lexicon_dir / "lexicon.json").write_text(json.dumps(payload), encoding="utf-8")
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)], lexicon_dir=lexicon_dir)
    return tmp_path / "bible.db", stats


def test_count_and_detail(tmp_path: Path) -> None:
    db, stats = _build(tmp_path, _lexicon_payload())
    assert stats.strongs_entries == 4  # type: ignore[attr-defined]
    conn = sqlite3.connect(db)
    entry = get_strongs(conn, "G26")
    assert entry is not None
    assert (entry.lemma, entry.transliteration, entry.gloss, entry.language) == (
        "ἀγάπη",
        "agapē",
        "love",
        "grc",
    )
    assert entry.definition == "love, goodwill, esteem."
    assert entry.source == "STEP Bible (Tyndale House)"


def test_empty_transliteration_allowed(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _lexicon_payload())
    conn = sqlite3.connect(db)
    entry = get_strongs(conn, "G21371")
    assert entry is not None
    assert entry.transliteration == ""
    assert entry.gloss == "inedible"


def test_get_strongs_miss_is_none(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _lexicon_payload())
    conn = sqlite3.connect(db)
    assert get_strongs(conn, "G99999") is None


def test_browse_filter_and_numeric_order(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _lexicon_payload())
    conn = sqlite3.connect(db)
    # 'love' matches both Greek glosses; ordered numerically within language (G25 before G26).
    page = list_strongs(conn, "love", None, 50, 0)
    assert [r.strongs_id for r in page.rows] == ["G25", "G26"]
    assert page.total == 2
    # transliteration substring also matches.
    assert [r.strongs_id for r in list_strongs(conn, "elōhîm", None, 50, 0).rows] == ["H430"]


def test_language_filter(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _lexicon_payload())
    conn = sqlite3.connect(db)
    page = list_strongs(conn, None, "hbo", 50, 0)
    assert [r.strongs_id for r in page.rows] == ["H430"]
    assert page.total == 1


def test_duplicate_id_rejected(tmp_path: Path) -> None:
    entries = _entries()
    entries.append({**entries[0]})  # second "G26"
    payload: dict[str, object] = {"source": "STEP Bible (Tyndale House)", "entries": entries}
    with pytest.raises(LoaderError, match="duplicate Strong's id"):
        _build(tmp_path, payload)


def test_build_is_idempotent(tmp_path: Path) -> None:
    first = _build(tmp_path, _lexicon_payload())[1]
    second = build_database(
        tmp_path / "bible.db", [_corpus(tmp_path)], lexicon_dir=tmp_path / "strongs"
    )
    assert first.strongs_entries == second.strongs_entries  # type: ignore[attr-defined]


def test_no_lexicon_dir_yields_zero(tmp_path: Path) -> None:
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])  # lexicon_dir omitted
    assert stats.strongs_entries == 0
