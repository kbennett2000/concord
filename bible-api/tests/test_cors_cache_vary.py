"""Cacheable responses carry ``Vary: Origin`` so a no-Origin cache entry can't be
replayed to a cross-origin ``fetch`` (CORS cache poisoning — surfaced by
concord-tutorial-web).

Starlette's ``CORSMiddleware`` (``allow_origins=["*"]``, credentials off) only adds
``Access-Control-Allow-Origin`` when the request carries an ``Origin`` header. Without
``Vary: Origin`` on the immutable response, a hard-cached no-Origin copy (no ``ACAO``)
gets reused for a later cross-origin fetch and the browser's CORS check fails.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def _vary_contains_origin(vary: str | None) -> bool:
    if not vary:
        return False
    return "origin" in {token.strip().lower() for token in vary.split(",")}


def test_vary_origin_on_200(client: TestClient) -> None:
    response = client.get("/v1/verses/John 3:16", params={"translations": "KJV"})
    assert response.status_code == 200
    assert _vary_contains_origin(response.headers.get("vary"))


def test_vary_origin_on_304(client: TestClient) -> None:
    etag = client.get("/v1/verses/John 3:16", params={"translations": "KJV"}).headers["etag"]
    response = client.get(
        "/v1/verses/John 3:16",
        params={"translations": "KJV"},
        headers={"If-None-Match": etag},
    )
    assert response.status_code == 304
    assert _vary_contains_origin(response.headers.get("vary"))


def test_origin_request_still_gets_wildcard_acao(client: TestClient) -> None:
    """Contract: with an Origin header the open-CORS posture is unchanged (``*``)."""
    response = client.get(
        "/v1/verses/John 3:16",
        params={"translations": "KJV"},
        headers={"Origin": "http://example.com"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
