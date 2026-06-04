"""Smoke test: the genuine signal that the package boundary works.

A passing test here means bible-api imported bible-core, FastAPI loaded, and the route
responds — the whole point of Slice 0.
"""
# TestClient.get()'s return type isn't fully resolved by pyright in this
# fastapi/starlette/httpx combination; the assertions below are still type-safe.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from bible_api.app import app
from fastapi.testclient import TestClient


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "translation_count": 0,
        "verse_count": 0,
    }
