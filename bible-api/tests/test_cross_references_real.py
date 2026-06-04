"""Integration: /v1/cross-references against a real bible.db (translations + cross-refs)."""
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
CROSS_REFS = REPO_ROOT / "data" / "cross-references"


def test_real_cross_references_for_john_3_16(tmp_path: Path) -> None:
    db_path = tmp_path / "bible.db"
    stats = build_database(db_path, [TRANSLATIONS], [CROSS_REFS])
    assert stats.cross_references > 340_000

    with TestClient(create_app(db_path=db_path)) as client:
        assert client.get("/healthz").json()["cross_ref_count"] == stats.cross_references
        body = client.get(
            "/v1/cross-references/John 3:16",
            params={"include_text": "true", "translation": "KJV", "limit": 50},
        ).json()

    targets = {e["to"]["reference"] for e in body["cross_references"]}
    assert "Romans 5:8" in targets  # the canonical John 3:16 cross-reference
    assert "1 John 4:9-10" in targets
    top = body["cross_references"][0]
    assert top["votes"] >= 1
    assert top["text"]  # hydrated KJV text present
