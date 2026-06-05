"""End-to-end semantic search over the real corpus — the proof it works. Integration.

Needs the baked embeddings.db (S1) and the fetched model (S0); skips cleanly without either.
Asserts appear-in-top-k (not exact rank) so it is meaningful without being brittle to model
specifics.

Run with: `uv run pytest -m integration`.
"""

from __future__ import annotations

import pytest
from bible_semantic.build import default_embeddings_path
from bible_semantic.model import model_dir
from bible_semantic.store import semantic_search

pytestmark = pytest.mark.integration

# Classic "do not be anxious / do not worry" passages (USFM book ids).
_EXPECTED = {("PHP", 4, 6), ("1PE", 5, 7)} | {("MAT", 6, v) for v in range(25, 35)}


def _require() -> None:
    if not default_embeddings_path().is_file():
        pytest.skip("embeddings.db not built — run scripts/build_embeddings.py")
    if not (model_dir() / "onnx" / "model.onnx").is_file():
        pytest.skip("model not present — run scripts/fetch_model.py")


def test_anxiety_query_surfaces_expected_verses() -> None:
    _require()
    results = semantic_search("do not be anxious", k=20)
    refs = {(r.book_id, r.chapter, r.verse) for r, _ in results}
    assert refs & _EXPECTED, f"no expected anxiety verse in top-20: {sorted(refs)}"

    # Results are ranked by descending cosine.
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
