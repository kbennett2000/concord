"""/v1/chapters/{book}/{chapter}: alias + USFM resolution, reference echo, errors."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_chapter_by_alias(client: TestClient) -> None:
    body = client.get("/v1/chapters/john/3", params={"translations": "KJV"}).json()
    assert body["reference"] == "John 3"
    assert len(body["verses"]) == 20


def test_chapter_by_usfm_code(client: TestClient) -> None:
    body = client.get("/v1/chapters/JHN/3", params={"translations": "KJV"}).json()
    assert body["reference"] == "John 3"
    assert len(body["verses"]) == 20


def test_chapter_grouped(client: TestClient) -> None:
    body = client.get(
        "/v1/chapters/john/4", params={"translations": "KJV", "format": "grouped"}
    ).json()
    assert len(body["translations"]["KJV"]) == 10


def test_unknown_book_is_404(client: TestClient) -> None:
    response = client.get("/v1/chapters/hezekiah/1")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_book"


def test_chapter_zero_is_422(client: TestClient) -> None:
    assert client.get("/v1/chapters/john/0").status_code == 422


def test_nonexistent_chapter_is_404(client: TestClient) -> None:
    response = client.get("/v1/chapters/john/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_verses_found"
