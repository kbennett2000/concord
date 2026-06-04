"""Integration: /v1/search against a real bible.db built from the committed PD data."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from pathlib import Path

import pytest
from bible_api.app import create_app
from bible_core.loader import build_database
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"


def test_real_search_finds_known_verse(tmp_path: Path) -> None:
    db_path = tmp_path / "bible.db"
    build_database(db_path, [TRANSLATIONS])
    with TestClient(create_app(db_path=db_path)) as client:
        body = client.get(
            "/v1/search", params={"q": "lamp unto my feet", "translation": "KJV"}
        ).json()

    assert body["total"] >= 1
    psalm = [h for h in body["hits"] if (h["book"], h["chapter"], h["verse"]) == ("PSA", 119, 105)]
    assert psalm, "expected Psalm 119:105 among the hits"
    assert "<mark>" in psalm[0]["snippet"]
