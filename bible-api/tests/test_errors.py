"""400 / 404 / 422 all use the consistent error envelope."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_envelope_structure(client: TestClient) -> None:
    body = client.get("/v1/verses/foo bar").json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message", "detail"}


def test_400_unparseable_reference(client: TestClient) -> None:
    response = client.get("/v1/verses/foo bar")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unparseable_reference"


def test_404_unknown_book(client: TestClient) -> None:
    response = client.get("/v1/verses/Hezekiah 1:1")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_book"


def test_404_no_verses_found(client: TestClient) -> None:
    response = client.get("/v1/verses/Genesis 999:1")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_verses_found"


def test_404_unknown_translation(client: TestClient) -> None:
    response = client.get("/v1/verses/John 3:16", params={"translations": "XYZ"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "unknown_translation"
    assert body["error"]["detail"]["translation"] == "XYZ"


def test_422_bad_format_uses_envelope(client: TestClient) -> None:
    response = client.get("/v1/verses/John 3:16", params={"format": "banana"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_parameter"
    assert "errors" in body["error"]["detail"]
