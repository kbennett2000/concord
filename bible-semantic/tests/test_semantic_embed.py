"""End-to-end embedding tests — require the fetched ONNX model, so marked integration.

Two parts:
  1. *Well-formed* — the vector is 768-dim float32 with unit L2 norm.
  2. *Semantically meaningful* — a related pair is closer in cosine than either is to an
     unrelated string. This is the guard that proves the CLS-pooling recipe is correct, not
     merely well-shaped: a wrong pooling produces unit vectors that fail this comparison.

Run with: `uv run pytest -m integration` (after `uv run python scripts/fetch_model.py`).
"""

from __future__ import annotations

import numpy as np
import pytest
from bible_semantic.model import EMBEDDING_DIM, embed_query, model_dir
from numpy.typing import NDArray

pytestmark = pytest.mark.integration


def _require_model() -> None:
    directory = model_dir()
    if (
        not (directory / "tokenizer.json").is_file()
        or not (directory / "onnx" / "model.onnx").is_file()
    ):
        pytest.skip(
            f"model not present under {directory} — run `uv run python scripts/fetch_model.py`"
        )


def _cosine(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
    # Vectors are L2-normalized, so cosine similarity is just the dot product.
    return float(np.dot(a, b))


def test_embedding_is_well_formed() -> None:
    _require_model()
    vec = embed_query("God is love")
    assert vec.shape == (EMBEDDING_DIM,)
    assert vec.dtype == np.float32
    assert np.isclose(float(np.linalg.norm(vec)), 1.0, atol=1e-4)


def test_embedding_is_semantically_meaningful() -> None:
    _require_model()
    related_a = embed_query("Do not be anxious about anything")
    related_b = embed_query("Cast your cares on him")
    unrelated = embed_query("a genealogy of the kings of Israel")

    related_sim = _cosine(related_a, related_b)
    unrelated_sim_a = _cosine(related_a, unrelated)
    unrelated_sim_b = _cosine(related_b, unrelated)

    assert related_sim > unrelated_sim_a
    assert related_sim > unrelated_sim_b
