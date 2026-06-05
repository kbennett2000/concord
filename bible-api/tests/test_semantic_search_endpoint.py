"""Fast /v1/semantic-search tests: param validation + the disabled-path 503. No model.

The shared ``client`` fixture builds the app with ``enable_semantic=False``, so these never
load the embedding model — validation (422) and translation resolution (404) run before the
store is touched, and a valid request short-circuits to 503 ``semantic_unavailable``.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_missing_q_is_422(client: TestClient) -> None:
    assert client.get("/v1/semantic-search").status_code == 422


def test_empty_q_is_422(client: TestClient) -> None:
    assert client.get("/v1/semantic-search", params={"q": ""}).status_code == 422


def test_limit_out_of_range_is_422(client: TestClient) -> None:
    assert client.get("/v1/semantic-search", params={"q": "x", "limit": 0}).status_code == 422
    assert client.get("/v1/semantic-search", params={"q": "x", "limit": 101}).status_code == 422


def test_min_score_out_of_range_is_422(client: TestClient) -> None:
    assert client.get("/v1/semantic-search", params={"q": "x", "min_score": 2}).status_code == 422
    assert client.get("/v1/semantic-search", params={"q": "x", "min_score": -2}).status_code == 422


def test_unknown_translation_is_404(client: TestClient) -> None:
    response = client.get("/v1/semantic-search", params={"q": "x", "translation": "XYZ"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_translation"


def test_valid_request_is_503_when_semantic_disabled(client: TestClient) -> None:
    response = client.get("/v1/semantic-search", params={"q": "love"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "semantic_unavailable"
