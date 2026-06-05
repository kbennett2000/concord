"""Corpus build tests — require bible.db + the fetched model, so marked integration.

Verifies the baked artifact: row count == WEB verse count with no gaps, a correct metadata
guard row, a known verse's vector present and unit-norm, and byte-identical idempotency.

Run with: `uv run pytest -m integration` (needs `bible.db` and `scripts/fetch_model.py`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest
from bible_semantic.build import build_embeddings, default_bible_db_path
from bible_semantic.model import EMBEDDING_DIM, MODEL_ID, MODEL_REVISION, model_dir

pytestmark = pytest.mark.integration

WEB_VERSE_COUNT = 31054  # translation WEB in the v1 corpus (bible.db)


def _require_inputs() -> Path:
    bible_db = default_bible_db_path()
    model = model_dir()
    if not bible_db.is_file():
        pytest.skip(f"bible.db not found at {bible_db} — build it via bible_core.loader")
    if not (model / "onnx" / "model.onnx").is_file():
        pytest.skip(f"model not present under {model} — run `python scripts/fetch_model.py`")
    return bible_db


@pytest.fixture(scope="module")
def full_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    bible_db = _require_inputs()
    out = tmp_path_factory.mktemp("embeddings") / "embeddings.db"
    stats = build_embeddings(out, bible_db)  # full WEB corpus
    assert stats.verses == WEB_VERSE_COUNT
    return out


def test_row_count_matches_web_with_no_gaps(full_db: Path) -> None:
    conn = sqlite3.connect(full_db)
    count = conn.execute("SELECT count(*) FROM verse_embeddings").fetchone()[0]
    distinct = conn.execute(
        "SELECT count(*) FROM (SELECT DISTINCT book_id, chapter, verse FROM verse_embeddings)"
    ).fetchone()[0]
    assert count == WEB_VERSE_COUNT
    assert distinct == count  # no duplicate or missing (book, chapter, verse)


def test_every_vector_is_float32_768(full_db: Path) -> None:
    conn = sqlite3.connect(full_db)
    bad = conn.execute(
        "SELECT count(*) FROM verse_embeddings WHERE vector IS NULL OR length(vector) != ?",
        (EMBEDDING_DIM * 4,),
    ).fetchone()[0]
    assert bad == 0


def test_metadata_row_is_correct(full_db: Path) -> None:
    conn = sqlite3.connect(full_db)
    rows = conn.execute(
        "SELECT model, model_revision, dim, translation, normalized, built_at FROM embedding_meta"
    ).fetchall()
    assert len(rows) == 1
    model, revision, dim, translation, normalized, built_at = rows[0]
    assert model == MODEL_ID
    assert revision == MODEL_REVISION
    assert dim == EMBEDDING_DIM
    assert translation == "WEB"
    assert normalized == 1
    assert built_at  # non-empty ISO timestamp


def test_known_verse_vector_present_and_unit_norm(full_db: Path) -> None:
    conn = sqlite3.connect(full_db)
    row = conn.execute(
        "SELECT vector FROM verse_embeddings WHERE book_id='JHN' AND chapter=3 AND verse=16"
    ).fetchone()
    assert row is not None
    vec = np.frombuffer(row[0], dtype=np.float32)
    assert vec.shape == (EMBEDDING_DIM,)
    assert np.isclose(float(np.linalg.norm(vec)), 1.0, atol=1e-4)


def test_build_is_idempotent_and_byte_identical(tmp_path: Path) -> None:
    bible_db = _require_inputs()
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    stats_a = build_embeddings(db_a, bible_db, limit=256)
    stats_b = build_embeddings(db_b, bible_db, limit=256)
    assert stats_a.verses == stats_b.verses == 256

    conn_a, conn_b = sqlite3.connect(db_a), sqlite3.connect(db_b)
    count_a = conn_a.execute("SELECT count(*) FROM verse_embeddings").fetchone()[0]
    count_b = conn_b.execute("SELECT count(*) FROM verse_embeddings").fetchone()[0]
    assert count_a == count_b == 256

    # Metadata matches except built_at (a wall-clock timestamp).
    meta = "model, model_revision, dim, translation, normalized"
    assert (
        conn_a.execute(f"SELECT {meta} FROM embedding_meta").fetchone()
        == conn_b.execute(f"SELECT {meta} FROM embedding_meta").fetchone()
    )

    # A spot verse (GEN 1:1 — first in canonical order, within the limit) is byte-identical.
    where = "WHERE book_id='GEN' AND chapter=1 AND verse=1"
    vec_a = conn_a.execute(f"SELECT vector FROM verse_embeddings {where}").fetchone()[0]
    vec_b = conn_b.execute(f"SELECT vector FROM verse_embeddings {where}").fetchone()[0]
    assert vec_a == vec_b
