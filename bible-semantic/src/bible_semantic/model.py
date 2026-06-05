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

# int8 is the project standard (IBM's official dynamic-quantized uint8 weights) — fp32
# weights (~1.25 GB) blow the deploy size target (SPEC §4). fp32 stays selectable for dev /
# re-deriving the quality baseline via CONCORD_MODEL_PRECISION=fp32. Precision is the
# inference path, not the stored-vector dtype (vectors are always float32).
DEFAULT_PRECISION = "int8"
_ONNX_FILENAMES = {"int8": "model_quint8_avx2.onnx", "fp32": "model.onnx"}

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


def model_precision() -> str:
    """The model precision to load — ``CONCORD_MODEL_PRECISION`` (default ``int8``).

    The corpus is embedded and queried at the *same* precision; ``store`` records it in
    ``embedding_meta`` and refuses a mismatch. ``fp32`` is for dev / baseline only.
    """
    precision = os.environ.get("CONCORD_MODEL_PRECISION", DEFAULT_PRECISION).strip().lower()
    if precision not in _ONNX_FILENAMES:
        raise ValueError(
            f"CONCORD_MODEL_PRECISION={precision!r} is invalid; expected one of "
            f"{sorted(_ONNX_FILENAMES)}."
        )
    return precision


def l2_normalize(vec: NDArray[np.float32]) -> NDArray[np.float32]:
    """L2-normalize a 1-D vector to unit length. Pure — testable without the model."""
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        raise ValueError("cannot L2-normalize a zero vector")
    return (vec / norm).astype(np.float32)


@lru_cache(maxsize=2)
def _load(precision: str) -> tuple[Tokenizer, ort.InferenceSession]:
    """Load (and cache) the tokenizer + ONNX session for ``precision``. Sessions are costly."""
    directory = model_dir()
    tok_path = directory / "tokenizer.json"
    onnx_path = directory / "onnx" / _ONNX_FILENAMES[precision]
    if not tok_path.is_file() or not onnx_path.is_file():
        raise FileNotFoundError(
            f"Embedding model ({precision}) not found under {directory}. "
            f"Run `python scripts/fetch_model.py` (or set CONCORD_MODEL_PATH). "
            f"Expected {tok_path} and {onnx_path}."
        )
    tokenizer = Tokenizer.from_file(str(tok_path))
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    return tokenizer, session


def embed_texts(texts: list[str]) -> NDArray[np.float32]:
    """Embed a batch of texts into an ``(N, 768)`` array of L2-normalized float32 vectors.

    Same recipe as a single query, batched: tokenize -> ONNX inference -> CLS pool ->
    L2-normalize. Sequences are right-padded to the batch's longest length; CLS pooling
    reads token 0, which is always a real token (never padding), and padded positions are
    masked out by the attention mask — so a batched result matches the single-input result.
    Raises ``FileNotFoundError`` if the model has not been fetched.
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    tokenizer, session = _load(model_precision())
    encodings = tokenizer.encode_batch(texts)
    max_len = max(len(enc.ids) for enc in encodings)
    input_ids = np.zeros((len(encodings), max_len), dtype=np.int64)
    attention_mask = np.zeros((len(encodings), max_len), dtype=np.int64)
    for i, enc in enumerate(encodings):
        length = len(enc.ids)
        input_ids[i, :length] = enc.ids
        attention_mask[i, :length] = enc.attention_mask

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

    cls = last_hidden_state[:, 0, :]  # CLS pooling: each row's first-token hidden state
    norms = np.linalg.norm(cls, axis=1, keepdims=True)
    if np.any(norms == 0.0):
        raise ValueError("cannot L2-normalize a zero vector")
    return (cls / norms).astype(np.float32)


def embed_query(text: str) -> NDArray[np.float32]:
    """Embed ``text`` into a 768-dim, L2-normalized float32 vector.

    Pipeline: tokenize -> ONNX inference -> CLS pool (first token) -> L2-normalize. Thin
    wrapper over :func:`embed_texts` (a one-row batch needs no padding) so there is a single
    inference code path. Raises ``FileNotFoundError`` if the model has not been fetched.
    """
    return embed_texts([text])[0]
