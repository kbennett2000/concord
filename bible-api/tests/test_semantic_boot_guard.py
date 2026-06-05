"""The model-vs-vectors guard at boot: a mismatched embeddings.db makes the app refuse to
start. Fast — load_store fails at the guard before any model is loaded.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
from bible_api.app import create_app
from bible_semantic.model import EMBEDDING_DIM, MODEL_ID
from bible_semantic.schema import create_embeddings_schema
from fastapi.testclient import TestClient


def _mismatched_embeddings_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    create_embeddings_schema(conn)
    conn.execute(
        "INSERT INTO embedding_meta "
        "(model, model_revision, dim, precision, translation, normalized, built_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            MODEL_ID,
            "not-the-pinned-revision",
            EMBEDDING_DIM,
            "int8",
            "WEB",
            1,
            "2026-01-01T00:00:00+00:00",
        ),
    )
    vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    vec[0] = 1.0
    conn.execute(
        "INSERT INTO verse_embeddings (book_id, chapter, verse, vector) VALUES (?, ?, ?, ?)",
        ("GEN", 1, 1, vec.tobytes()),
    )
    conn.commit()
    conn.close()
    return path


def test_app_refuses_to_start_on_model_vectors_mismatch(db_path: Path, tmp_path: Path) -> None:
    bad = _mismatched_embeddings_db(tmp_path / "embeddings.db")
    app = create_app(db_path=db_path, enable_semantic=True, embeddings_path=bad)
    # The guard failure surfaces when the lifespan runs on TestClient startup.
    with pytest.raises(RuntimeError), TestClient(app):
        pass
