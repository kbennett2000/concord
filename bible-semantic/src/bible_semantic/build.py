"""Build-time corpus embedding generator (docs/v2/SPEC.md §8).

Reads every verse of one translation (WEB by default) from ``bible.db`` via ``bible-core``,
embeds each with the S0 pipeline (batched), and writes the vectors plus a single
``embedding_meta`` guard row into a freshly-built ``embeddings.db``. Rebuilds from scratch
each run (idempotent) and fails loudly on a missing model or an empty corpus.

``bible-core`` is used only to *read* ``bible.db`` (never touched directly); ``embeddings.db``
is this package's own artifact, written with stdlib ``sqlite3``.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bible_core.db import connect_readonly
from bible_core.queries import VerseRow, iter_verses

from .model import EMBEDDING_DIM, MODEL_ID, MODEL_REVISION, embed_texts, model_precision
from .schema import create_embeddings_schema

DEFAULT_TRANSLATION = "WEB"
DEFAULT_BATCH_SIZE = 64


class BuildError(Exception):
    """Raised when the corpus build cannot proceed (e.g. an empty corpus)."""


@dataclass(frozen=True)
class EmbeddingBuildStats:
    """Summary of a completed embeddings build."""

    translation: str
    verses: int
    dim: int
    batch_size: int
    elapsed_seconds: float


def default_embeddings_path() -> Path:
    """``embeddings.db`` location; override with ``CONCORD_EMBEDDINGS_PATH`` (mirrors S0)."""
    override = os.environ.get("CONCORD_EMBEDDINGS_PATH")
    if override:
        return Path(override)
    # parents: build.py -> bible_semantic -> src -> bible-semantic -> <repo root>
    return Path(__file__).resolve().parents[3] / "embeddings.db"


def default_bible_db_path() -> Path:
    """``bible.db`` location; reuses v1's ``BIBLE_DB_PATH`` env (default ``bible.db``)."""
    return Path(os.environ.get("BIBLE_DB_PATH", "bible.db"))


def _chunks(items: list[VerseRow], size: int) -> Iterator[list[VerseRow]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def build_embeddings(
    embeddings_db_path: Path,
    bible_db_path: Path,
    translation_id: str = DEFAULT_TRANSLATION,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
) -> EmbeddingBuildStats:
    """Embed ``translation_id`` from ``bible_db_path`` into a fresh ``embeddings_db_path``.

    Idempotent: deletes and rebuilds the database from scratch. ``limit`` (default ``None`` =
    full corpus) embeds only the first N verses — for fast partial/dev/test builds.
    """
    if batch_size < 1:
        raise BuildError(f"batch_size must be >= 1, got {batch_size}")
    start = time.perf_counter()

    src = connect_readonly(bible_db_path)
    try:
        verses = list(iter_verses(src, translation_id))
    finally:
        src.close()
    if limit is not None:
        verses = verses[:limit]
    if not verses:
        raise BuildError(
            f"no verses found for translation {translation_id!r} in {bible_db_path} — "
            "nothing to embed (is the translation present and bible.db built?)."
        )

    embeddings_db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(embeddings_db_path)
    try:
        create_embeddings_schema(conn)
        with conn:
            for batch in _chunks(verses, batch_size):
                vectors = embed_texts([v.text for v in batch])
                conn.executemany(
                    "INSERT INTO verse_embeddings (book_id, chapter, verse, vector) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        (v.book_id, v.chapter, v.verse, vec.tobytes())
                        for v, vec in zip(batch, vectors, strict=True)
                    ],
                )
            conn.execute(
                "INSERT INTO embedding_meta "
                "(model, model_revision, dim, precision, translation, normalized, built_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    MODEL_ID,
                    MODEL_REVISION,
                    EMBEDDING_DIM,
                    model_precision(),
                    translation_id,
                    1,
                    datetime.now(UTC).isoformat(),
                ),
            )
    finally:
        conn.close()

    return EmbeddingBuildStats(
        translation=translation_id,
        verses=len(verses),
        dim=EMBEDDING_DIM,
        batch_size=batch_size,
        elapsed_seconds=time.perf_counter() - start,
    )
