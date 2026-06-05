"""Pure cosine top-k: ranking, k limit, min_score floor, deterministic ties. No model."""

from __future__ import annotations

import numpy as np
from bible_semantic.search import cosine_top_k
from numpy.typing import NDArray


def _unit(*components: float) -> NDArray[np.float32]:
    vec = np.asarray(components, dtype=np.float32)
    return (vec / np.linalg.norm(vec)).astype(np.float32)


# Four unit vectors. Against query [1,0,0]: row0 cos=1.0, row2 cos≈0.707, rows 1 & 3 cos=0.0.
_MATRIX = np.stack([_unit(1, 0, 0), _unit(0, 1, 0), _unit(1, 1, 0), _unit(0, 0, 1)])
_REFS = ["a", "b", "c", "d"]
_QUERY = _unit(1, 0, 0)


def test_ranks_by_cosine_descending_with_index_tiebreak() -> None:
    result = cosine_top_k(_QUERY, _MATRIX, _REFS, k=4)
    # a (1.0), c (~.707), then the b/d tie broken by ascending index → b before d.
    assert [ref for ref, _ in result] == ["a", "c", "b", "d"]
    assert abs(result[0][1] - 1.0) < 1e-5
    assert abs(result[1][1] - 0.70710677) < 1e-5
    assert abs(result[2][1]) < 1e-6


def test_k_limits_results() -> None:
    result = cosine_top_k(_QUERY, _MATRIX, _REFS, k=2)
    assert [ref for ref, _ in result] == ["a", "c"]


def test_min_score_filters_before_topk() -> None:
    result = cosine_top_k(_QUERY, _MATRIX, _REFS, k=4, min_score=0.5)
    assert [ref for ref, _ in result] == ["a", "c"]  # b, d (0.0) dropped


def test_min_score_can_exclude_everything() -> None:
    assert cosine_top_k(_QUERY, _MATRIX, _REFS, k=4, min_score=1.1) == []


def test_non_positive_k_returns_empty() -> None:
    assert cosine_top_k(_QUERY, _MATRIX, _REFS, k=0) == []


def test_k_larger_than_corpus_is_clamped() -> None:
    result = cosine_top_k(_QUERY, _MATRIX, _REFS, k=99)
    assert len(result) == 4
