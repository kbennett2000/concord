"""Integration: /v1/semantic-search over the real corpus (bible.db + embeddings.db + model).

Exercises the endpoint mechanics — result shape, the cross-translation hydrate, include_text,
ETag round-trip, and /healthz readiness — against the real baked artifacts. Skips cleanly
when any of bible.db, embeddings.db, or the model is absent.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from bible_api.app import create_app
from bible_semantic.model import EMBEDDING_DIM, MODEL_ID, model_dir
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[2]
_BIBLE_DB = _REPO / "bible.db"
_EMBEDDINGS_DB = _REPO / "embeddings.db"

# Classic "do not be anxious / do not worry" verses (USFM book ids).
_EXPECTED = {("PHP", 4, 6), ("1PE", 5, 7)} | {("MAT", 6, v) for v in range(25, 35)}


@pytest.fixture(scope="module")
def semantic_client() -> Iterator[TestClient]:
    if not _BIBLE_DB.is_file() or not _EMBEDDINGS_DB.is_file():
        pytest.skip("real bible.db + embeddings.db required (build them first)")
    if not (model_dir() / "onnx" / "model.onnx").is_file():
        pytest.skip("model not present — run scripts/fetch_model.py")
    app = create_app(db_path=_BIBLE_DB, enable_semantic=True, embeddings_path=_EMBEDDINGS_DB)
    with TestClient(app) as client:
        yield client


def test_real_query_shape_and_relevance(semantic_client: TestClient) -> None:
    body = semantic_client.get("/v1/semantic-search", params={"q": "do not be anxious"}).json()
    assert body["translation"] == "WEB"  # default display = embedded translation
    assert body["count"] == len(body["results"])
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)  # ranked descending
    first = body["results"][0]
    assert set(first) == {"book", "chapter", "verse", "reference", "score", "text"}
    assert isinstance(first["text"], str)  # WEB text hydrated by default
    refs = {(r["book"], r["chapter"], r["verse"]) for r in body["results"]}
    assert refs & _EXPECTED, f"no expected anxiety verse in results: {sorted(refs)}"


def test_limit_is_honored(semantic_client: TestClient) -> None:
    body = semantic_client.get(
        "/v1/semantic-search", params={"q": "do not be anxious", "limit": 3}
    ).json()
    assert body["count"] <= 3


def test_include_text_false_omits_text(semantic_client: TestClient) -> None:
    body = semantic_client.get(
        "/v1/semantic-search", params={"q": "love", "include_text": "false"}
    ).json()
    assert body["results"]
    assert all(r["text"] is None for r in body["results"])


def test_cross_translation_hydrate(semantic_client: TestClient) -> None:
    body = semantic_client.get(
        "/v1/semantic-search", params={"q": "the good shepherd", "translation": "KJV"}
    ).json()
    assert body["translation"] == "KJV"
    # At least most results have KJV text (search ran in WEB space; text is KJV).
    assert any(isinstance(r["text"], str) for r in body["results"])


def test_etag_round_trip(semantic_client: TestClient) -> None:
    params = {"q": "do not be anxious", "limit": "5"}
    first = semantic_client.get("/v1/semantic-search", params=params)
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert first.headers["cache-control"]

    second = semantic_client.get(
        "/v1/semantic-search", params=params, headers={"If-None-Match": etag}
    )
    assert second.status_code == 304
    assert second.content == b""


def test_healthz_reports_semantic_readiness(semantic_client: TestClient) -> None:
    semantic = semantic_client.get("/healthz").json()["semantic"]
    assert semantic["enabled"] is True
    assert semantic["translation"] == "WEB"
    assert semantic["embedding_count"] == 31054
    assert semantic["model"] == MODEL_ID
    assert semantic["dim"] == EMBEDDING_DIM
