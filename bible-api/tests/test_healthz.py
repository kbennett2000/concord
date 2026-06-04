"""/healthz now reports real loaded-translation and verse counts from the DB.

(Slice 0 returned hardcoded zeros; Slice 4 wires it to the seeded test corpus. The
boundary still holds — bible-api imports bible-core, FastAPI loads, the route responds.)
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_reports_real_counts(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["translation_count"] == 3  # KJV, WEB, YLT in the test corpus
    # 59 (John 3, WEB omits one) + 30 (John 4) + 9 (Gen 1) + 9 (1 John 1) = 107
    assert body["verse_count"] == 107
    assert body["cross_ref_count"] == 5  # seeded by apikit.build_corpus
    assert body["book_count"] == 66
