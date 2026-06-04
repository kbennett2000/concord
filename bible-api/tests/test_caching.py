"""ETag, Cache-Control, and the If-None-Match → 304 round-trip (SPEC §7)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient

CACHE_CONTROL = "public, max-age=31536000, immutable"


def _etag(client: TestClient, ref: str, translations: str = "KJV") -> str:
    return client.get(f"/v1/verses/{ref}", params={"translations": translations}).headers["etag"]


def test_cache_control_header(client: TestClient) -> None:
    response = client.get("/v1/verses/John 3:16", params={"translations": "KJV"})
    assert response.headers["cache-control"] == CACHE_CONTROL


def test_etag_is_stable_for_same_request(client: TestClient) -> None:
    assert _etag(client, "John 3:16") == _etag(client, "John 3:16")


def test_etag_differs_by_reference(client: TestClient) -> None:
    assert _etag(client, "John 3:16") != _etag(client, "John 3:17")


def test_etag_differs_by_translation_set(client: TestClient) -> None:
    assert _etag(client, "John 3:17", "KJV") != _etag(client, "John 3:17", "KJV,WEB")


def test_if_none_match_returns_304_no_body(client: TestClient) -> None:
    etag = _etag(client, "John 3:16")
    response = client.get(
        "/v1/verses/John 3:16",
        params={"translations": "KJV"},
        headers={"If-None-Match": etag},
    )
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == etag
    assert response.headers["cache-control"] == CACHE_CONTROL
