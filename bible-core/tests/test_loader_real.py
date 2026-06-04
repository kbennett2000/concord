"""Integration: build from the real committed PD translations and check reality.

Excluded from the default run (``-m "not integration"``); run with ``pytest -m integration``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import build_database

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"


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

    # 13 committed public-domain translations (data/private is not scanned here).
    assert stats.translations == 13
    assert conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0] == 13
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
