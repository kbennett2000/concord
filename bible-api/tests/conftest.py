"""Shared fixtures: a built synthetic corpus and a TestClient wired to it (session-scoped)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from apikit import build_corpus
from bible_api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("corpus") / "bible.db"
    build_corpus(path)
    return path


@pytest.fixture(scope="session")
def client(db_path: Path) -> Iterator[TestClient]:
    # Semantic search disabled here so the fast suite never loads the embedding model;
    # endpoint validation (422/404) and the 503-when-disabled path need no model. Real
    # semantic results are exercised by the integration-marked tests with their own app.
    app = create_app(db_path=db_path, enable_semantic=False)
    with TestClient(app) as test_client:
        yield test_client
