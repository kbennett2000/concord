"""Missing-verse semantics (synthetic fixture: WEB omits John 3:16)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from apikit import verse_text
from fastapi.testclient import TestClient


def test_parallel_nulls_the_omitting_translation(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:16", params={"translations": "KJV,WEB"}).json()
    verse = body["verses"][0]
    assert verse["verse"] == 16
    assert verse["text"]["KJV"] == verse_text("JHN", 3, 16, "KJV")
    assert verse["text"]["WEB"] is None


def test_grouped_omits_the_verse_from_that_translation(client: TestClient) -> None:
    body = client.get(
        "/v1/verses/John 3:16", params={"translations": "KJV,WEB", "format": "grouped"}
    ).json()
    assert [v["verse"] for v in body["translations"]["KJV"]] == [16]
    assert body["translations"]["WEB"] == []  # present as a key, but empty


def test_range_returns_union_with_nullfill(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:16-17", params={"translations": "KJV,WEB"}).json()
    texts = {v["verse"]: v["text"] for v in body["verses"]}
    assert texts[16]["KJV"] is not None
    assert texts[16]["WEB"] is None
    assert texts[17]["KJV"] is not None
    assert texts[17]["WEB"] is not None


def test_verse_only_in_omitting_translation_is_404(client: TestClient) -> None:
    # WEB lacks John 3:16, so requesting only WEB yields no verses → 404.
    response = client.get("/v1/verses/John 3:16", params={"translations": "WEB"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_verses_found"
