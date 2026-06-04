"""Malformed translation input fails loudly with a specific LoaderError."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from bible_core.loader import LoaderError, build_database
from loaderkit import book, chapter, translation, verse, write_translation


def _build_one(tmp_path: Path, payload: dict[str, Any]) -> None:
    tdir = tmp_path / "translations"
    write_translation(tdir, payload, filename="t.json")
    build_database(tmp_path / "bible.db", [tdir])


def test_missing_code(tmp_path: Path) -> None:
    tdir = tmp_path / "translations"
    tdir.mkdir(parents=True)
    (tdir / "bad.json").write_text(
        json.dumps({"name": "X", "language": "en", "copyright": "PD", "books": []})
    )
    with pytest.raises(LoaderError, match="missing required field 'code'"):
        build_database(tmp_path / "bible.db", [tdir])


def test_unresolvable_book_code(tmp_path: Path) -> None:
    payload = translation("T", [book("ZZZ", 1, [chapter(1, [verse(1, "x")])])])
    with pytest.raises(LoaderError, match="does not resolve"):
        _build_one(tmp_path, payload)


def test_order_index_mismatch(tmp_path: Path) -> None:
    payload = translation("T", [book("Gen", 2, [chapter(1, [verse(1, "x")])])])
    with pytest.raises(LoaderError, match="inconsistent book identity"):
        _build_one(tmp_path, payload)


def test_non_integer_chapter_number(tmp_path: Path) -> None:
    tdir = tmp_path / "translations"
    tdir.mkdir(parents=True)
    payload = {
        "code": "T",
        "name": "X",
        "language": "en",
        "copyright": "PD",
        "books": [
            {
                "abbreviation": "Gen",
                "name": "Gen",
                "order_index": 1,
                "chapters": [{"number": "one", "verses": [{"number": 1, "text": "x"}]}],
            }
        ],
    }
    (tdir / "t.json").write_text(json.dumps(payload))
    with pytest.raises(LoaderError, match="must be an integer"):
        build_database(tmp_path / "bible.db", [tdir])


def test_invalid_json(tmp_path: Path) -> None:
    tdir = tmp_path / "translations"
    tdir.mkdir(parents=True)
    (tdir / "t.json").write_text("{not valid json")
    with pytest.raises(LoaderError, match="invalid JSON"):
        build_database(tmp_path / "bible.db", [tdir])


def test_cross_translation_chapter_count_disagreement(tmp_path: Path) -> None:
    tdir = tmp_path / "translations"
    two_chapters = book("Gen", 1, [chapter(1, [verse(1, "x")]), chapter(2, [verse(1, "y")])])
    one_chapter = book("Gen", 1, [chapter(1, [verse(1, "x")])])
    write_translation(tdir, translation("AAA", [two_chapters]), filename="a.json")
    write_translation(tdir, translation("BBB", [one_chapter]), filename="b.json")
    with pytest.raises(LoaderError, match="disagree on the chapter count"):
        build_database(tmp_path / "bible.db", [tdir])


def test_empty_data_dir(tmp_path: Path) -> None:
    tdir = tmp_path / "translations"
    tdir.mkdir(parents=True)
    with pytest.raises(LoaderError, match="No translation JSON"):
        build_database(tmp_path / "bible.db", [tdir])
