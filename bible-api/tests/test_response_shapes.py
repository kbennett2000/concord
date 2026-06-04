"""Byte-precise SPEC §7 shapes: exact key order and structure for both formats."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_parallel_key_order(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:17", params={"translations": "KJV,WEB"}).json()
    assert list(body.keys()) == ["reference", "translations", "verses"]
    assert list(body["verses"][0].keys()) == ["book", "chapter", "verse", "reference", "text"]
    # text dict keys follow requested-translation order
    assert list(body["verses"][0]["text"].keys()) == ["KJV", "WEB"]


def test_grouped_key_order(client: TestClient) -> None:
    body = client.get(
        "/v1/verses/John 3:17", params={"translations": "KJV,WEB", "format": "grouped"}
    ).json()
    assert list(body.keys()) == ["reference", "translations"]
    assert list(body["translations"].keys()) == ["KJV", "WEB"]
    assert list(body["translations"]["KJV"][0].keys()) == ["book", "chapter", "verse", "text"]


def test_content_type_is_json(client: TestClient) -> None:
    response = client.get("/v1/verses/John 3:17", params={"translations": "KJV"})
    assert response.headers["content-type"] == "application/json"
