"""Deterministic tests for the /v1/semantic-search wall-clock deadline (ADR-0002).

No wall-clock races: the timeout path is forced by making the (monkeypatched) inference block
on a ``threading.Event`` the test controls, so the work never completes and *any* positive
deadline fires deterministically. The under-deadline path uses an instant callable with a
generous deadline. Together they prove the three load-bearing properties:

* the deadline returns 503 ``semantic_timeout`` + ``Retry-After``;
* a timed-out (zombie) inference keeps holding its permit until it finishes, so a concurrent
  request is shed with ``semantic_busy`` and only succeeds once the worker drains — the cap
  stays coupled to real CPU (the ADR-0001 invariant ADR-0002 must not break);
* a zero deadline disables the executor entirely (ADR-0001 behaviour, unchanged).
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest
from bible_api.app import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient

# A stand-in for the real VectorStore (see test_semantic_concurrency.py): the handler passes
# .matrix/.refs to cosine_top_k (patched to a no-op) and reads .meta.translation.
_STUB_STORE = SimpleNamespace(matrix=None, refs=[], meta=SimpleNamespace(translation="WEB"))

# (cap, timeout, embed callable) -> (client, app)
ClientFactory = Callable[..., tuple[TestClient, FastAPI]]


@pytest.fixture
def make_semantic_client(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ClientFactory]:
    monkeypatch.setattr("bible_api.routers.cosine_top_k", lambda *a, **k: [])
    with ExitStack() as stack:

        def _make(
            cap: int, timeout: float, embed: Callable[[str], object] | None = None
        ) -> tuple[TestClient, FastAPI]:
            monkeypatch.setattr("bible_api.routers.embed_query", embed or (lambda q: None))
            app = create_app(
                db_path=db_path,
                enable_semantic=False,
                semantic_max_concurrency=cap,
                semantic_timeout_s=timeout,
            )
            client = stack.enter_context(TestClient(app))
            app.state.semantic_store = _STUB_STORE  # proceed past the `store is None` check
            return client, app

        yield _make


def test_deadline_exceeded_sheds_503_timeout(make_semantic_client: ClientFactory) -> None:
    ev = threading.Event()
    client, _ = make_semantic_client(1, 0.05, lambda q: ev.wait())  # never completes in-request
    try:
        response = client.get("/v1/semantic-search", params={"q": "love"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "semantic_timeout"
        assert response.headers["retry-after"] == "1"
    finally:
        ev.set()  # let the zombie worker drain and release its permit


def test_zombie_holds_permit_until_drained(make_semantic_client: ClientFactory) -> None:
    ev = threading.Event()
    client, app = make_semantic_client(1, 0.05, lambda q: ev.wait())
    try:
        # Request A times out; its worker is still blocked on the event, holding the only permit.
        a = client.get("/v1/semantic-search", params={"q": "a"})
        assert a.status_code == 503
        assert a.json()["error"]["code"] == "semantic_timeout"
        # Request B: the cap is full because the zombie still holds the permit → shed as busy,
        # NOT timeout. This is the proof the cap stays coupled to real CPU.
        b = client.get("/v1/semantic-search", params={"q": "b"})
        assert b.status_code == 503
        assert b.json()["error"]["code"] == "semantic_busy"
    finally:
        ev.set()
    # Once the zombie finishes it releases the permit; acquiring it proves the release happened.
    assert app.state.semantic_semaphore.acquire(timeout=5)
    app.state.semantic_semaphore.release()
    # The event is now set, so a fresh inference returns instantly → request C succeeds.
    assert client.get("/v1/semantic-search", params={"q": "c"}).status_code == 200


def test_timeout_zero_disables_executor(make_semantic_client: ClientFactory) -> None:
    client, app = make_semantic_client(1, 0.0)
    assert app.state.semantic_executor is None
    assert app.state.semantic_timeout_s == 0.0
    # With a cap but no deadline, the synchronous ADR-0001 path runs — still 200.
    assert client.get("/v1/semantic-search", params={"q": "love"}).status_code == 200


def test_no_cap_means_no_executor(make_semantic_client: ClientFactory) -> None:
    client, app = make_semantic_client(0, 30.0)
    # A deadline needs a permit to couple to; with no cap there is nothing to protect.
    assert app.state.semantic_semaphore is None
    assert app.state.semantic_executor is None
    assert client.get("/v1/semantic-search", params={"q": "love"}).status_code == 200


def test_under_deadline_succeeds_and_reuses_slot(make_semantic_client: ClientFactory) -> None:
    client, app = make_semantic_client(1, 30.0)
    assert app.state.semantic_executor is not None  # cap on + positive timeout → executor active
    assert client.get("/v1/semantic-search", params={"q": "a"}).status_code == 200
    # The worker released the permit on success → the second request reuses the slot.
    assert client.get("/v1/semantic-search", params={"q": "b"}).status_code == 200
