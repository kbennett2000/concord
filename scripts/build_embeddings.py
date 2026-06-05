#!/usr/bin/env python3
"""Build embeddings.db from a translation's verses (docs/v2/SPEC.md §8).

A thin CLI over ``bible_semantic.build.build_embeddings``. Rebuilds from scratch each run.
Runs at build time (the model is fetched beforehand via scripts/fetch_model.py); the
runtime never embeds the corpus.

    uv run python scripts/build_embeddings.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bible_semantic.build import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_TRANSLATION,
    BuildError,
    build_embeddings,
    default_bible_db_path,
    default_embeddings_path,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/build_embeddings.py",
        description="Embed a translation's verses into embeddings.db (rebuilds from scratch).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(default_embeddings_path()),
        help="output embeddings database path (env CONCORD_EMBEDDINGS_PATH; default embeddings.db)",
    )
    parser.add_argument(
        "--bible-db",
        default=str(default_bible_db_path()),
        help="input bible.db path (env BIBLE_DB_PATH; default bible.db)",
    )
    parser.add_argument(
        "--translation", default=DEFAULT_TRANSLATION, help="translation to embed (default: WEB)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="embedding batch size"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="embed only the first N verses (partial build)"
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the summary line")
    args = parser.parse_args(argv)

    try:
        stats = build_embeddings(
            Path(args.output),
            Path(args.bible_db),
            translation_id=args.translation,
            batch_size=args.batch_size,
            limit=args.limit,
        )
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(
            f"Built {args.output}: {stats.verses} {stats.translation} verses "
            f"@ dim {stats.dim}, batch {stats.batch_size}, in {stats.elapsed_seconds:.1f}s."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
