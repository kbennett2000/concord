"""Vector store loader + the model-vs-vectors guard. Fast — load_store never runs the model."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
from bible_semantic.model import DEFAULT_PRECISION, EMBEDDING_DIM, MODEL_ID, MODEL_REVISION
from bible_semantic.schema import create_embeddings_schema
from bible_semantic.store import StoreError, VerseRef, load_store


def _make_db(
    path: Path,
    *,
    model: str = MODEL_ID,
    revision: str = MODEL_REVISION,
    dim: int = EMBEDDING_DIM,
    precision: str = DEFAULT_PRECISION,
    normalized: int = 1,
    rows: list[tuple[str, int, int]] | None = None,
) -> Path:
    rows = rows if rows is not None else [("JHN", 3, 16), ("GEN", 1, 1)]
    conn = sqlite3.connect(path)
    create_embeddings_schema(conn)
    conn.execute(
        "INSERT INTO embedding_meta "
        "(model, model_revision, dim, precision, translation, normalized, built_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (model, revision, dim, precision, "WEB", normalized, "2026-01-01T00:00:00+00:00"),
    )
    for book_id, chapter, verse in rows:
        vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        vec[0] = 1.0  # a real-width unit vector
        conn.execute(
            "INSERT INTO verse_embeddings (book_id, chapter, verse, vector) VALUES (?, ?, ?, ?)",
            (book_id, chapter, verse, vec.tobytes()),
        )
    conn.commit()
    conn.close()
    return path


def test_loads_valid_store(tmp_path: Path) -> None:
    store = load_store(_make_db(tmp_path / "e.db"))
    assert store.matrix.shape == (2, EMBEDDING_DIM)
    assert store.matrix.dtype == np.float32
    # Ordered by book_id, chapter, verse → GEN before JHN.
    assert store.refs == [VerseRef("GEN", 1, 1), VerseRef("JHN", 3, 16)]
    assert store.meta.model == MODEL_ID
    assert store.meta.model_revision == MODEL_REVISION
    assert store.meta.dim == EMBEDDING_DIM


def test_guard_rejects_wrong_model(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="model"):
        load_store(_make_db(tmp_path / "e.db", model="some/other-model"))


def test_guard_rejects_wrong_revision(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="revision"):
        load_store(_make_db(tmp_path / "e.db", revision="deadbeef" * 5))


def test_guard_rejects_wrong_dim(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="dim"):
        load_store(_make_db(tmp_path / "e.db", dim=256))


def test_guard_rejects_unnormalized(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="normalized"):
        load_store(_make_db(tmp_path / "e.db", normalized=0))


def test_guard_rejects_precision_mismatch(tmp_path: Path) -> None:
    # An fp32-built corpus under the default int8 query model → refuse (query and corpus
    # must share precision to compare correctly).
    with pytest.raises(StoreError, match="precision"):
        load_store(_make_db(tmp_path / "e.db", precision="fp32"))


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="not found"):
        load_store(tmp_path / "absent.db")


def test_empty_corpus_raises(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="no vectors"):
        load_store(_make_db(tmp_path / "e.db", rows=[]))
