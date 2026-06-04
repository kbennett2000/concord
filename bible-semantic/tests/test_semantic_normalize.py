"""Unit tests for the pure L2-normalize step. No model required — runs in the fast suite."""

from __future__ import annotations

import numpy as np
import pytest
from bible_semantic.model import l2_normalize


def test_normalizes_to_unit_length() -> None:
    vec = np.array([3.0, 4.0], dtype=np.float32)  # norm 5
    out = l2_normalize(vec)
    assert out.dtype == np.float32
    assert np.isclose(float(np.linalg.norm(out)), 1.0, atol=1e-6)
    # Direction is preserved.
    assert np.allclose(out, np.array([0.6, 0.8], dtype=np.float32), atol=1e-6)


def test_already_unit_vector_is_stable() -> None:
    vec = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    out = l2_normalize(vec)
    assert np.allclose(out, vec, atol=1e-6)


def test_zero_vector_raises() -> None:
    with pytest.raises(ValueError):
        l2_normalize(np.zeros(4, dtype=np.float32))
