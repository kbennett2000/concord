"""Deterministic tests for the /v1/semantic-search concurrency cap (ADR-0001 / HS-8).

No threads, no sleeps, no real inference. The guard reaches a stub semantic store with the
compute monkeypatched to no-ops, and "cap full" is simulated by pre-holding the semaphore
permit from the test thread — so the handler's non-blocking acquire deterministically fails
regardless of scheduling.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest
from bible_api.app import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient

# A stand-in for the real VectorStore: the handler passes .matrix/.refs to cosine_top_k
# (patched to a no-op) and reads .meta.translation when ?translation= is omitted.
_STUB_STORE = SimpleNamespace(matrix=None, refs=[], meta=SimpleNamespace(translation="WEB"))

ClientFactory = Callable[[int], tuple[TestClient, FastAPI]]


@pytest.fixture
def make_semantic_client(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ClientFactory]:
    # No-op the expensive compute so the guard runs without the real ONNX model.
    monkeypatch.setattr("bible_api.routers.embed_query", lambda q: None)
    monkeypatch.setattr("bible_api.routers.cosine_top_k", lambda *a, **k: [])
    with ExitStack() as stack:

        def _make(cap: int) -> tuple[TestClient, FastAPI]:
            app = create_app(db_path=db_path, enable_semantic=False, semantic_max_concurrency=cap)
            client = stack.enter_context(TestClient(app))
            # Inject a store so the handler proceeds past the `store is None` check.
            app.state.semantic_store = _STUB_STORE
            return client, app

        yield _make


def test_under_cap_succeeds(make_semantic_client: ClientFactory) -> None:
    client, _ = make_semantic_client(2)
    response = client.get("/v1/semantic-search", params={"q": "love"})
    assert response.status_code == 200
    assert response.json()["count"] == 0  # patched cosine returns no matches


def test_cap_full_sheds_503_with_envelope_and_retry_after(
    make_semantic_client: ClientFactory,
) -> None:
    client, app = make_semantic_client(1)
    # Deterministically occupy the only permit from the test thread.
    assert app.state.semantic_semaphore.acquire(blocking=False)
    try:
        response = client.get("/v1/semantic-search", params={"q": "love"})
    finally:
        app.state.semantic_semaphore.release()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "semantic_busy"
    assert response.headers["retry-after"] == "1"


def test_slot_released_after_request(make_semantic_client: ClientFactory) -> None:
    client, _ = make_semantic_client(1)
    assert client.get("/v1/semantic-search", params={"q": "a"}).status_code == 200
    # If the first request didn't release the permit, this second one would 503.
    assert client.get("/v1/semantic-search", params={"q": "b"}).status_code == 200


def test_cap_zero_is_inert(make_semantic_client: ClientFactory) -> None:
    client, app = make_semantic_client(0)
    assert app.state.semantic_semaphore is None  # no guard at all
    assert client.get("/v1/semantic-search", params={"q": "love"}).status_code == 200


def test_disabled_semantic_never_engages_guard(db_path: Path) -> None:
    # No stub store → store is None → 503 semantic_unavailable, never semantic_busy.
    app = create_app(db_path=db_path, enable_semantic=False, semantic_max_concurrency=1)
    with TestClient(app) as client:
        response = client.get("/v1/semantic-search", params={"q": "love"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "semantic_unavailable"


def test_fts5_search_unaffected_by_full_cap(make_semantic_client: ClientFactory) -> None:
    client, app = make_semantic_client(1)
    # Even with the semantic permit fully held, the keyword /search path is untouched.
    assert app.state.semantic_semaphore.acquire(blocking=False)
    try:
        response = client.get("/v1/search", params={"q": "God", "translation": "KJV"})
    finally:
        app.state.semantic_semaphore.release()
    assert response.status_code == 200
