"""Interactive docs are fully offline — no CDN URLs, assets served locally (SPEC §3).

Kept in the default suite (not integration) so a future FastAPI upgrade that flips /docs
back to its CDN defaults fails immediately.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# Hosts FastAPI's defaults would reach (jsdelivr/unpkg for the bundles, googleapis for
# ReDoc's fonts, fastapi.tiangolo.com for the favicon).
FORBIDDEN = ["jsdelivr", "unpkg", "cdn.", "fonts.googleapis", "fastapi.tiangolo.com"]


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_docs_html_has_no_cdn_urls(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    html = response.text
    assert "/static/" in html  # references the vendored assets
    for marker in FORBIDDEN:
        assert marker not in html, f"{path} still reaches a CDN ({marker})"


@pytest.mark.parametrize(
    "asset",
    [
        "/static/swagger-ui/swagger-ui-bundle.js",
        "/static/swagger-ui/swagger-ui.css",
        "/static/swagger-ui/favicon-32x32.png",
        "/static/redoc/redoc.standalone.js",
    ],
)
def test_vendored_assets_are_served(client: TestClient, asset: str) -> None:
    assert client.get(asset).status_code == 200


def test_openapi_json_still_served(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200
