"""Integration: /books, /translations, /random, /healthz against a real bible.db."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from bible_api.app import create_app
from bible_core.loader import build_database
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"


def test_utility_endpoints_against_real_db(tmp_path: Path) -> None:
    db_path = tmp_path / "bible.db"
    build_database(db_path, [TRANSLATIONS])

    # chapter_count must match MAX(chapter) from verses (real data is contiguous from 1)
    conn = sqlite3.connect(db_path)
    max_chapters = dict(conn.execute("SELECT book_id, MAX(chapter) FROM verses GROUP BY book_id"))

    with TestClient(create_app(db_path=db_path)) as client:
        books = client.get("/v1/books").json()["books"]
        assert len(books) == 66
        by_id = {b["id"]: b for b in books}
        assert by_id["GEN"]["chapter_count"] == 50
        assert by_id["PSA"]["chapter_count"] == 150
        for book in books:
            assert book["chapter_count"] == max_chapters[book["id"]]

        translations = client.get("/v1/translations").json()["translations"]
        # 13 PD English + the Greek SBLGNT + the Hebrew OSHB (both CC BY, STEPBible)
        assert len(translations) == 15
        assert all(t["attribution"] for t in translations)
        oshb = next(t for t in translations if t["id"] == "OSHB")
        assert (oshb["language"], oshb["direction"]) == ("hbo", "rtl")

        ot_verse = client.get("/v1/random", params={"testament": "OT"}).json()["verse"]
        assert by_id[ot_verse["book"]]["testament"] == "OT"

        assert client.get("/healthz").json()["book_count"] == 66
