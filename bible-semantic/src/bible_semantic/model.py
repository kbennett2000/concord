"""Query-embedding core for Concord's semantic layer.

Embeds a single text string into a 768-dimensional, L2-normalized vector using the
``granite-embedding-311m-multilingual-r2`` ONNX model — no PyTorch, no transformers, no
sentence-transformers. The pipeline (verified against the model card in Slice S0):

    tokenize  ->  ONNX inference  ->  CLS pool (token 0)  ->  L2-normalize

The model uses **CLS pooling** (the first/``[CLS]`` token's hidden state), **not**
mean-pooling, and applies **no dense projection** before normalization. Because the output
is L2-normalized, cosine similarity later reduces to a dot product (see docs/v2/SPEC.md §5).
"""

# onnxruntime ships no type stubs, so its InferenceSession surface (get_inputs/run) is
# dynamically typed. Scope the stub/unknown-type suppression to this thin wrapper module
# only — every other file in the package stays under full pyright-strict checking.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray
from tokenizers import Tokenizer

# The model, pinned to an exact revision for reproducible fetches (see scripts/fetch_model.py).
MODEL_ID = "ibm-granite/granite-embedding-311m-multilingual-r2"
MODEL_REVISION = "44399559930365213510b1ee2eb15ded83374f0e"
EMBEDDING_DIM = 768

# Default location of the fetched weights, under the gitignored repo-root models/ directory.
# parents: model.py -> bible_semantic -> src -> bible-semantic -> <repo root>.
_DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / MODEL_ID.split("/")[-1]


def model_dir() -> Path:
    """Directory holding the ONNX weights + tokenizer.

    Defaults to ``<repo>/models/granite-embedding-311m-multilingual-r2``; override with the
    ``CONCORD_MODEL_PATH`` environment variable (mirrors v1's env-config style).
    """
    override = os.environ.get("CONCORD_MODEL_PATH")
    return Path(override) if override else _DEFAULT_MODEL_DIR


def l2_normalize(vec: NDArray[np.float32]) -> NDArray[np.float32]:
    """L2-normalize a 1-D vector to unit length. Pure — testable without the model."""
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        raise ValueError("cannot L2-normalize a zero vector")
    return (vec / norm).astype(np.float32)


@lru_cache(maxsize=1)
def _load() -> tuple[Tokenizer, ort.InferenceSession]:
    """Load (and cache) the tokenizer + ONNX session. Sessions are expensive to build."""
    directory = model_dir()
    tok_path = directory / "tokenizer.json"
    onnx_path = directory / "onnx" / "model.onnx"
    if not tok_path.is_file() or not onnx_path.is_file():
        raise FileNotFoundError(
            f"Embedding model not found under {directory}. "
            f"Run `python scripts/fetch_model.py` (or set CONCORD_MODEL_PATH). "
            f"Expected {tok_path} and {onnx_path}."
        )
    tokenizer = Tokenizer.from_file(str(tok_path))
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    return tokenizer, session


def embed_query(text: str) -> NDArray[np.float32]:
    """Embed ``text`` into a 768-dim, L2-normalized float32 vector.

    Pipeline: tokenize -> ONNX inference -> CLS pool (first token) -> L2-normalize.
    Raises ``FileNotFoundError`` if the model has not been fetched.
    """
    tokenizer, session = _load()
    encoding = tokenizer.encode(text)
    input_ids: NDArray[np.int64] = np.asarray([encoding.ids], dtype=np.int64)
    attention_mask: NDArray[np.int64] = np.asarray([encoding.attention_mask], dtype=np.int64)

    # Feed only the inputs the graph declares. ModernBERT takes input_ids + attention_mask;
    # this stays correct if a variant export also wants token_type_ids.
    available = {node.name for node in session.get_inputs()}
    feed: dict[str, NDArray[np.int64]] = {}
    if "input_ids" in available:
        feed["input_ids"] = input_ids
    if "attention_mask" in available:
        feed["attention_mask"] = attention_mask
    if "token_type_ids" in available:
        feed["token_type_ids"] = np.zeros_like(input_ids)

    outputs = session.run(None, feed)
    last_hidden_state: NDArray[np.float32] = np.asarray(outputs[0], dtype=np.float32)
    if last_hidden_state.ndim != 3 or last_hidden_state.shape[-1] != EMBEDDING_DIM:
        raise ValueError(
            f"unexpected ONNX output shape {last_hidden_state.shape}; "
            f"expected (batch, seq_len, {EMBEDDING_DIM})"
        )

    cls_vector = last_hidden_state[0, 0, :]  # CLS pooling: the first token's hidden state
    return l2_normalize(cls_vector)
