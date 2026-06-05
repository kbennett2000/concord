"""Pure cosine top-k over a normalized embedding matrix.

No I/O, no model, no DB: given a query vector and a matrix of L2-normalized verse vectors,
return the top-k most similar refs by cosine similarity — which is a plain dot product, since
every vector is unit-normalized. Fully unit-testable with a tiny synthetic matrix.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

import numpy as np
from numpy.typing import NDArray

T = TypeVar("T")


def cosine_top_k(
    query_vec: NDArray[np.float32],
    matrix: NDArray[np.float32],
    refs: Sequence[T],
    k: int,
    min_score: float | None = None,
) -> list[tuple[T, float]]:
    """Return up to ``k`` ``(ref, score)`` pairs, highest cosine similarity first.

    Cosine == dot product because ``matrix`` rows and ``query_vec`` are L2-normalized.
    ``min_score`` (if given) is a cosine floor on ``[-1, 1]`` applied *before* the top-k cut.
    Ties break by ascending row index for determinism. Returns ``[]`` for ``k <= 0`` or when
    nothing clears the floor; returns fewer than ``k`` when the corpus or floor limits it.
    """
    if k <= 0:
        return []

    scores: NDArray[np.float32] = matrix @ query_vec  # (N,) — cosine == dot (unit vectors)
    # Order all rows by score descending, ties broken by ascending index (deterministic).
    indices: NDArray[np.intp] = np.arange(int(scores.shape[0]))
    neg_scores: NDArray[np.float32] = -scores
    order: NDArray[np.intp] = np.lexsort((indices, neg_scores))
    ranked: list[int] = order.tolist()

    result: list[tuple[T, float]] = []
    for idx in ranked:
        score = float(scores[idx])
        if min_score is not None and score < min_score:
            break  # descending order: once below the floor, every remaining row is too
        result.append((refs[idx], score))
        if len(result) >= k:
            break
    return result
