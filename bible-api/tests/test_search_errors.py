"""/v1/search error paths, all using the consistent envelope from Slice 4."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_missing_q_is_422(client: TestClient) -> None:
    assert client.get("/v1/search").status_code == 422


def test_empty_q_is_422(client: TestClient) -> None:
    assert client.get("/v1/search", params={"q": ""}).status_code == 422


def test_malformed_query_is_400(client: TestClient) -> None:
    response = client.get("/v1/search", params={"q": '"unbalanced', "translation": "KJV"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_search_query"
    assert "fts5_error" in body["error"]["detail"]


def test_unknown_translation_is_404(client: TestClient) -> None:
    response = client.get("/v1/search", params={"q": "gen", "translation": "XYZ"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_translation"


def test_unknown_book_filter_is_400(client: TestClient) -> None:
    response = client.get("/v1/search", params={"q": "gen", "book": "hezekiah"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_book"


def test_limit_too_large_is_422(client: TestClient) -> None:
    assert client.get("/v1/search", params={"q": "gen", "limit": 101}).status_code == 422


def test_limit_zero_is_422(client: TestClient) -> None:
    assert client.get("/v1/search", params={"q": "gen", "limit": 0}).status_code == 422


def test_envelope_matches_verses_endpoint(client: TestClient) -> None:
    search_error = client.get("/v1/search", params={"q": '"unbalanced'}).json()
    verses_error = client.get("/v1/verses/foo bar").json()
    assert set(search_error.keys()) == set(verses_error.keys()) == {"error"}
    assert set(search_error["error"].keys()) == set(verses_error["error"].keys())
