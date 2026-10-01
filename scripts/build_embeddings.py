#!/usr/bin/env python3
"""Build embeddings.db from a translation's verses (docs/v2/SPEC.md §8).

A thin CLI over ``bible_semantic.build``. Rebuilds from scratch each run. Runs at build time
(the model is fetched beforehand via scripts/fetch_model.py); the runtime never embeds the
corpus.

    uv run python scripts/build_embeddings.py

The Docker build splits the run in two (V8-S1b): ``--export-verses`` writes the WEB verse list
beside bible.db, and a separate stage embeds it with ``--verses``, needing no bible-core — so
that stage's cache keys on the verse text alone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bible_semantic.build import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_TRANSLATION,
    BuildError,
    EmbeddingBuildStats,
    build_embeddings,
    default_bible_db_path,
    default_embeddings_path,
    embed_corpus,
    read_corpus,
    read_verse_list,
    write_verse_list,
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
    split = parser.add_mutually_exclusive_group()
    split.add_argument(
        "--export-verses",
        metavar="PATH",
        help="write the translation's verse list (read from --bible-db) to PATH, embed nothing",
    )
    split.add_argument(
        "--verses",
        metavar="PATH",
        help="embed a verse list written by --export-verses instead of reading --bible-db",
    )
    args = parser.parse_args(argv)

    try:
        if args.export_verses:
            verses = read_corpus(Path(args.bible_db), args.translation)
            if not verses:
                raise BuildError(f"no {args.translation!r} verses in {args.bible_db} to export.")
            write_verse_list(Path(args.export_verses), args.translation, verses)
            if not args.quiet:
                print(f"Wrote {args.export_verses}: {len(verses)} {args.translation} verses.")
            return 0
        stats = _embed(args)
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


def _embed(args: argparse.Namespace) -> EmbeddingBuildStats:
    if not args.verses:
        return build_embeddings(
            Path(args.output),
            Path(args.bible_db),
            translation_id=args.translation,
            batch_size=args.batch_size,
            limit=args.limit,
        )
    translation, verses = read_verse_list(Path(args.verses))
    if args.limit is not None:
        verses = verses[: args.limit]
    return embed_corpus(Path(args.output), verses, translation, args.batch_size)


if __name__ == "__main__":
    sys.exit(main())
