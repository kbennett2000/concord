"""The exported verse list — the Docker embeddings stage's only corpus input (V8-S1b).

The Docker build writes the WEB verse list beside bible.db (``--export-verses``) and embeds it
in a stage with no bible-core installed (``--verses``), so the embedding's cache keys on the
verse text alone. These fast tests (synthetic bible.db, no model) pin what that relies on: the
same bible.db gives a byte-identical list, the list reads back exactly, a bad list fails loudly,
and the embedding entry point imports without bible-core.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import build_embeddings as cli  # scripts/build_embeddings.py (pytest pythonpath = scripts)
import pytest
from bible_core.loader import build_database
from bible_semantic.build import BuildError, CorpusVerse, read_verse_list

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_embeddings.py"


def _book(abbreviation: str, order_index: int, number: int, verses: list[str]) -> object:
    return {
        "abbreviation": abbreviation,
        "name": abbreviation,
        "order_index": order_index,
        "chapters": [
            {
                "number": number,
                "verses": [{"number": i, "text": t} for i, t in enumerate(verses, start=1)],
            }
        ],
    }


def _synthetic_db(tmp_path: Path) -> Path:
    """One translation through the real loader; John is listed before Genesis on purpose."""
    data_dir = tmp_path / "translations"
    data_dir.mkdir()
    payload = {
        "code": "TST",
        "name": "Test Version",
        "language": "en",
        "copyright": "Public domain.",
        "books": [
            _book("John", 43, 3, ["Made-up words, “quoted”.", "More made-up words."]),
            _book("Gen", 1, 1, ["In the made-up beginning."]),
        ],
    }
    (data_dir / "tst.json").write_text(json.dumps(payload), encoding="utf-8")
    db_path = tmp_path / "bible.db"
    build_database(db_path, [data_dir])
    return db_path


def _export(db: Path, out: Path) -> None:
    argv = ["--bible-db", str(db), "--translation", "TST", "--export-verses", str(out), "--quiet"]
    assert cli.main(argv) == 0


def test_export_is_byte_identical_for_the_same_bible_db(tmp_path: Path) -> None:
    db = _synthetic_db(tmp_path)
    _export(db, tmp_path / "a.json")
    _export(db, tmp_path / "b.json")
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def test_export_reads_back_in_canonical_order(tmp_path: Path) -> None:
    out = tmp_path / "verses.json"
    _export(_synthetic_db(tmp_path), out)
    assert read_verse_list(out) == (
        "TST",
        [
            CorpusVerse("GEN", 1, 1, "In the made-up beginning."),
            CorpusVerse("JHN", 3, 1, "Made-up words, “quoted”."),
            CorpusVerse("JHN", 3, 2, "More made-up words."),
        ],
    )


def test_export_of_a_missing_translation_fails(tmp_path: Path) -> None:
    db = _synthetic_db(tmp_path)
    out = tmp_path / "verses.json"
    assert cli.main(["--bible-db", str(db), "--export-verses", str(out), "--quiet"]) == 1  # WEB
    assert not out.exists()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"verses": []},
        {"translation": "TST"},
        {"translation": "TST", "verses": [["GEN", 1, 1]]},
        {"translation": "TST", "verses": [["GEN", "1", 1, "text"]]},
    ],
)
def test_a_malformed_verse_list_fails_loudly(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "verses.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BuildError):
        read_verse_list(path)


def test_embedding_entry_point_imports_without_bible_core() -> None:
    """The Docker embeddings stage has no bible-core: the script must import and parse args."""
    code = (
        "import runpy, sys\n"
        "sys.modules['bible_core'] = None  # any `import bible_core...` now raises ImportError\n"
        f"sys.argv = [{str(_SCRIPT)!r}, '--help']\n"
        f"runpy.run_path({str(_SCRIPT)!r}, run_name='__main__')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "--verses" in result.stdout
