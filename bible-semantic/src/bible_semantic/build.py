"""Build-time corpus embedding generator (docs/v2/SPEC.md §8).

Reads every verse of one translation (WEB by default) from ``bible.db`` via ``bible-core``,
embeds each with the S0 pipeline (batched), and writes the vectors plus a single
``embedding_meta`` guard row into a freshly-built ``embeddings.db``. Rebuilds from scratch
each run (idempotent) and fails loudly on a missing model or an empty corpus.

``bible-core`` is used only to *read* ``bible.db`` (never touched directly); ``embeddings.db``
is this package's own artifact, written with stdlib ``sqlite3``.

The read and the embed can also run apart, through a **verse list** file (V8-S1b): the Docker
build exports the WEB verse list next to ``bible.db`` and embeds it in a stage with no
``bible-core`` installed, so that stage's cache keys on the verse text alone. Hence
``bible-core`` is imported inside ``read_corpus`` only — this module imports without it.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from .model import EMBEDDING_DIM, MODEL_ID, MODEL_REVISION, embed_texts, model_precision
from .schema import create_embeddings_schema

DEFAULT_TRANSLATION = "WEB"
DEFAULT_BATCH_SIZE = 64


class BuildError(Exception):
    """Raised when the corpus build cannot proceed (e.g. an empty corpus)."""


@dataclass(frozen=True)
class CorpusVerse:
    """One verse to embed: its key and its text."""

    book_id: str
    chapter: int
    verse: int
    text: str


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


def _chunks(items: Sequence[CorpusVerse], size: int) -> Iterator[Sequence[CorpusVerse]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def read_corpus(
    bible_db_path: Path, translation_id: str = DEFAULT_TRANSLATION
) -> list[CorpusVerse]:
    """Every verse of ``translation_id`` in ``bible_db_path``, in canonical order."""
    # Imported here, not at module top: the Docker embeddings stage runs this module with no
    # bible-core installed (it embeds an exported verse list), so a bible-core code change
    # never invalidates the cached embeddings.
    from bible_core.db import connect_readonly
    from bible_core.queries import iter_verses

    src = connect_readonly(bible_db_path)
    try:
        return [
            CorpusVerse(book_id=v.book_id, chapter=v.chapter, verse=v.verse, text=v.text)
            for v in iter_verses(src, translation_id)
        ]
    finally:
        src.close()


def write_verse_list(path: Path, translation_id: str, verses: Sequence[CorpusVerse]) -> None:
    """Write ``verses`` as a verse list: deterministic, so the same verses give the same bytes."""
    payload = {
        "translation": translation_id,
        "verses": [[v.book_id, v.chapter, v.verse, v.text] for v in verses],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def read_verse_list(path: Path) -> tuple[str, list[CorpusVerse]]:
    """Read a verse list written by ``write_verse_list``: ``(translation_id, verses)``."""
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BuildError(f"{path}: a verse list is a JSON object")
    fields = cast("dict[str, object]", payload)
    translation_id = fields.get("translation")
    rows = fields.get("verses")
    if not isinstance(translation_id, str) or not isinstance(rows, list):
        raise BuildError(f"{path}: a verse list needs a 'translation' string and a 'verses' list")
    verses: list[CorpusVerse] = []
    for row in cast("list[object]", rows):
        match row:
            case [str(book_id), int(chapter), int(verse), str(text)]:
                verses.append(CorpusVerse(book_id, chapter, verse, text))
            case _:
                raise BuildError(f"{path}: bad verse row {row!r}")
    return translation_id, verses


def embed_corpus(
    embeddings_db_path: Path,
    verses: Sequence[CorpusVerse],
    translation_id: str = DEFAULT_TRANSLATION,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> EmbeddingBuildStats:
    """Embed ``verses`` (of ``translation_id``) into a fresh ``embeddings_db_path``.

    Idempotent: deletes and rebuilds the database from scratch. Needs no ``bible-core``.
    """
    if batch_size < 1:
        raise BuildError(f"batch_size must be >= 1, got {batch_size}")
    if not verses:
        raise BuildError(f"no {translation_id!r} verses to embed.")
    start = time.perf_counter()

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
    verses = read_corpus(bible_db_path, translation_id)
    if limit is not None:
        verses = verses[:limit]
    if not verses:
        raise BuildError(
            f"no verses found for translation {translation_id!r} in {bible_db_path} — "
            "nothing to embed (is the translation present and bible.db built?)."
        )
    return embed_corpus(embeddings_db_path, verses, translation_id, batch_size)
