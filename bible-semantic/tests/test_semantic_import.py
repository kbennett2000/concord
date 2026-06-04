"""bible-semantic imports cleanly and exposes its embedding constants. No model needed."""

from __future__ import annotations

from pathlib import Path

import bible_semantic
from bible_semantic.model import EMBEDDING_DIM, MODEL_ID, MODEL_REVISION, model_dir


def test_version_is_exposed() -> None:
    assert isinstance(bible_semantic.__version__, str)
    assert bible_semantic.__version__


def test_model_constants() -> None:
    assert MODEL_ID == "ibm-granite/granite-embedding-311m-multilingual-r2"
    assert EMBEDDING_DIM == 768
    # A pinned 40-char git revision, not a moving branch name.
    assert len(MODEL_REVISION) == 40
    assert all(c in "0123456789abcdef" for c in MODEL_REVISION)


def test_model_dir_is_a_path() -> None:
    assert isinstance(model_dir(), Path)
