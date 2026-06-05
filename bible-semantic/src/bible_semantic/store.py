"""In-memory vector store, the model-vs-vectors guard, and search orchestration.

Loads ``embeddings.db`` (S1's baked artifact) into a contiguous numpy matrix held once in
memory, **refusing to load** if the running model's identity does not match the metadata the
vectors were built with — returning garbage similarities is worse than failing loudly.
``semantic_search`` embeds a query (via ``model.py``) and runs the pure cosine top-k
(``search.py``) over the loaded store; it is exactly what S2b's HTTP endpoint will call.

Orchestration lives here rather than in ``search.py`` so that module stays pure.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from .build import default_embeddings_path
from .model import EMBEDDING_DIM, MODEL_ID, MODEL_REVISION, embed_query, model_precision
from .schema import EMBEDDING_META_TABLE, VERSE_EMBEDDINGS_TABLE
from .search import cosine_top_k


class StoreError(Exception):
    """Raised when ``embeddings.db`` is missing, empty, malformed, or model-mismatched."""


@dataclass(frozen=True)
class VerseRef:
    """A verse position (USFM book id + chapter + verse) — no text (hydration is S2b)."""

    book_id: str
    chapter: int
    verse: int


@dataclass(frozen=True)
class EmbeddingMeta:
    """The single ``embedding_meta`` guard row."""

    model: str
    model_revision: str
    dim: int
    precision: str
    translation: str
    normalized: int
    built_at: str


@dataclass(frozen=True)
class VectorStore:
    """The loaded vectors: an ``(N, dim)`` L2-normalized matrix + parallel refs + metadata."""

    matrix: NDArray[np.float32]
    refs: list[VerseRef]
    meta: EmbeddingMeta


def _read_meta(conn: sqlite3.Connection) -> EmbeddingMeta:
    row = conn.execute(
        f"SELECT model, model_revision, dim, precision, translation, normalized, built_at "
        f"FROM {EMBEDDING_META_TABLE}"
    ).fetchone()
    if row is None:
        raise StoreError("embeddings.db has no embedding_meta row")
    return EmbeddingMeta(*row)


def _check_guard(meta: EmbeddingMeta) -> None:
    """Refuse to serve vectors built by a different model/revision/dim than the running code."""
    mismatches: list[str] = []
    if meta.model != MODEL_ID:
        mismatches.append(f"model {meta.model!r} != running {MODEL_ID!r}")
    if meta.model_revision != MODEL_REVISION:
        mismatches.append(f"model_revision {meta.model_revision!r} != running {MODEL_REVISION!r}")
    if meta.dim != EMBEDDING_DIM:
        mismatches.append(f"dim {meta.dim} != running {EMBEDDING_DIM}")
    running_precision = model_precision()
    if meta.precision != running_precision:
        mismatches.append(f"precision {meta.precision!r} != running {running_precision!r}")
    if meta.normalized != 1:
        mismatches.append(f"normalized {meta.normalized} != 1 (search assumes unit vectors)")
    if mismatches:
        raise StoreError(
            "embeddings.db was built with a different model than the running code — "
            "refusing to serve mismatched vectors: " + "; ".join(mismatches)
        )


def load_store(path: Path | None = None) -> VectorStore:
    """Read ``embeddings.db`` into a ``VectorStore``, running the guard. Raises ``StoreError``.

    Pure of global state — tests call this directly; production uses :func:`get_store`.
    """
    db_path = path or default_embeddings_path()
    if not db_path.is_file():
        raise StoreError(
            f"embeddings.db not found at {db_path}. Build it with scripts/build_embeddings.py "
            "(or set CONCORD_EMBEDDINGS_PATH)."
        )

    conn = sqlite3.connect(db_path)
    try:
        meta = _read_meta(conn)
        _check_guard(meta)
        rows = conn.execute(
            f"SELECT book_id, chapter, verse, vector FROM {VERSE_EMBEDDINGS_TABLE} "
            "ORDER BY book_id, chapter, verse"
        ).fetchall()
    finally:
        conn.close()

    n = len(rows)
    if n == 0:
        raise StoreError("embeddings.db contains no vectors — nothing to search")

    matrix = np.empty((n, meta.dim), dtype=np.float32)
    refs: list[VerseRef] = []
    expected_bytes = meta.dim * 4  # float32
    for i, (book_id, chapter, verse, blob) in enumerate(rows):
        if len(blob) != expected_bytes:
            raise StoreError(
                f"vector for {book_id} {chapter}:{verse} is {len(blob)} bytes, "
                f"expected {expected_bytes} ({meta.dim} x float32)"
            )
        matrix[i] = np.frombuffer(blob, dtype=np.float32)
        refs.append(VerseRef(book_id, chapter, verse))

    return VectorStore(matrix=matrix, refs=refs, meta=meta)


_store: VectorStore | None = None


def get_store() -> VectorStore:
    """Return the process-wide store, loading it once (default path) on first call.

    The ~95 MB matrix is held in memory for the process lifetime — never re-read per query.
    S2b's FastAPI lifespan can call this at startup to load eagerly instead of on first hit.
    """
    global _store
    if _store is None:
        _store = load_store()
    return _store


def semantic_search(
    query: str, k: int, min_score: float | None = None
) -> list[tuple[VerseRef, float]]:
    """Embed ``query`` and return up to ``k`` nearest verses by cosine similarity."""
    store = get_store()
    query_vec = embed_query(query)
    return cosine_top_k(query_vec, store.matrix, store.refs, k, min_score)
