"""/v1/cross-references error + caching paths, reusing the Slice 4/5 envelope and ETag."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient

CACHE_CONTROL = "public, max-age=31536000, immutable"


def test_out_of_range_is_404(client: TestClient) -> None:
    response = client.get("/v1/cross-references/Genesis 999:1")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_verses_found"


def test_unknown_book_is_404(client: TestClient) -> None:
    response = client.get("/v1/cross-references/Hezekiah 1:1")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_book"


def test_unparseable_is_400(client: TestClient) -> None:
    response = client.get("/v1/cross-references/foo bar")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unparseable_reference"


def test_negative_min_votes_is_422(client: TestClient) -> None:
    assert client.get("/v1/cross-references/John 3:16", params={"min_votes": -1}).status_code == 422


def test_limit_too_large_is_422(client: TestClient) -> None:
    assert client.get("/v1/cross-references/John 3:16", params={"limit": 101}).status_code == 422


def test_include_text_unknown_translation_is_404(client: TestClient) -> None:
    response = client.get(
        "/v1/cross-references/John 3:16", params={"include_text": "true", "translation": "XYZ"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_translation"


def test_envelope_matches_verses_endpoint(client: TestClient) -> None:
    xref_error = client.get("/v1/cross-references/foo bar").json()
    verses_error = client.get("/v1/verses/foo bar").json()
    assert set(xref_error.keys()) == set(verses_error.keys()) == {"error"}
    assert set(xref_error["error"].keys()) == set(verses_error["error"].keys())


def test_cache_control_and_etag_304(client: TestClient) -> None:
    response = client.get("/v1/cross-references/John 3:16")
    assert response.headers["cache-control"] == CACHE_CONTROL
    etag = response.headers["etag"]
    not_modified = client.get("/v1/cross-references/John 3:16", headers={"If-None-Match": etag})
    assert not_modified.status_code == 304
    assert not_modified.content == b""


def test_etag_differs_by_include_text(client: TestClient) -> None:
    plain = client.get("/v1/cross-references/John 3:16").headers["etag"]
    hydrated = client.get(
        "/v1/cross-references/John 3:16", params={"include_text": "true", "translation": "KJV"}
    ).headers["etag"]
    assert plain != hydrated
