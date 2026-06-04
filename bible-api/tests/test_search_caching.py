"""/v1/search reuses Slice 4's ETag + Cache-Control + 304 (body-hashed)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient

CACHE_CONTROL = "public, max-age=31536000, immutable"


def _etag(client: TestClient, **params: object) -> str:
    return client.get("/v1/search", params=params).headers["etag"]


def test_cache_control_header(client: TestClient) -> None:
    response = client.get("/v1/search", params={"q": "gen", "translation": "KJV"})
    assert response.headers["cache-control"] == CACHE_CONTROL


def test_same_query_same_etag(client: TestClient) -> None:
    assert _etag(client, q="gen", translation="KJV") == _etag(client, q="gen", translation="KJV")


def test_etag_differs_by_query(client: TestClient) -> None:
    assert _etag(client, q="gen", translation="KJV") != _etag(client, q="jhn", translation="KJV")


def test_etag_differs_by_offset(client: TestClient) -> None:
    a = _etag(client, q="jhn", translation="KJV", limit=5, offset=0)
    b = _etag(client, q="jhn", translation="KJV", limit=5, offset=5)
    assert a != b


def test_etag_differs_by_book_filter(client: TestClient) -> None:
    a = _etag(client, q="gen", translation="KJV")
    b = _etag(client, q="gen", translation="KJV", book="genesis")
    assert a != b


def test_if_none_match_returns_304(client: TestClient) -> None:
    etag = _etag(client, q="gen", translation="KJV")
    response = client.get(
        "/v1/search",
        params={"q": "gen", "translation": "KJV"},
        headers={"If-None-Match": etag},
    )
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == etag
