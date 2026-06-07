#!/usr/bin/env python3
"""Embed Concord in-process — query Scripture with no HTTP server running.

`bible-core`'s headline is that it has **zero web dependencies**, so a Python program can
import it directly and read Scripture without `bible-api`, FastAPI, Uvicorn, or a socket
anywhere in sight. This script is the concrete proof: it opens a built `bible.db`, parses a
reference, and fetches a verse — all in-process.

It then *optionally* does a semantic search through `bible-semantic` (also web-free). That half
needs the embedding model and the vector store, which aren't part of a plain `bible.db` build,
so it degrades gracefully: if either is missing the script says so and still exits 0.

Run it against a database you've built (`make build-db`)::

    uv run python examples/embed_in_process.py
    uv run python examples/embed_in_process.py --ref "Romans 8:28" --translation WEB \
        --query "nothing can separate us from love"

Nothing here touches the network, and the core path imports only `bible_core`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from bible_core.db import connect_readonly
from bible_core.parser import Reference, parse_reference
from bible_core.queries import get_verse_text
from bible_core.resolver import SqliteBookResolver

DEFAULT_DB_PATH = os.environ.get("BIBLE_DB_PATH", "bible.db")


def fetch_verse_in_process(
    db_path: str | Path, ref_text: str, translation: str
) -> tuple[Reference, str | None]:
    """Parse ``ref_text`` and fetch its first verse's text in ``translation`` — no HTTP.

    Returns the parsed :class:`~bible_core.parser.Reference` and the verse text (``None`` if
    that translation omits the verse). Uses only ``bible_core``: a read-only connection, the
    SQLite-backed book resolver, the pure reference parser, and a single query function.
    """
    conn = connect_readonly(db_path)
    try:
        resolver = SqliteBookResolver(conn)
        reference = parse_reference(ref_text, resolver)
        span = reference.spans[0]
        # The example reference points at a single verse; start_verse is None only for a
        # whole-chapter selection (e.g. "John 3"), which this script doesn't fetch.
        if span.start_verse is None:
            return reference, None
        text = get_verse_text(
            conn, translation.upper(), reference.book_id, span.start_chapter, span.start_verse
        )
        return reference, text
    finally:
        conn.close()


def semantic_search_in_process(
    db_path: str | Path, query: str, k: int = 5
) -> list[tuple[str, float, str | None]] | None:
    """Embed ``query`` and return the top-``k`` verses by meaning — or ``None`` if unavailable.

    Guarded by the semantic extra: if ``bible_semantic`` isn't installed, or the embedding
    model / vector store hasn't been built, this returns ``None`` so the caller can skip it.
    Each result is ``(reference, score, text)`` with the verse hydrated through ``bible_core``.
    """
    try:
        from bible_semantic.model import embed_query
        from bible_semantic.search import cosine_top_k
        from bible_semantic.store import StoreError, load_store
    except ImportError:
        return None

    try:
        store = load_store()
    except StoreError:
        return None
    try:
        query_vec = embed_query(query)
    except FileNotFoundError:
        # The ONNX weights haven't been fetched (scripts/fetch_model.py).
        return None

    conn = connect_readonly(db_path)
    try:
        hits = cosine_top_k(query_vec, store.matrix, store.refs, k)
        return [
            (
                f"{ref.book_id} {ref.chapter}:{ref.verse}",
                score,
                get_verse_text(conn, store.meta.translation, ref.book_id, ref.chapter, ref.verse),
            )
            for ref, score in hits
        ]
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="path to a built bible.db")
    parser.add_argument("--ref", default="John 3:16", help="a Scripture reference to fetch")
    parser.add_argument("--translation", default="KJV", help="translation id for the fetch")
    parser.add_argument("--query", default="God so loved the world", help="semantic-search query")
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(
            f"No database at {args.db!r}. Build one with `make build-db`, or pass --db.",
            file=sys.stderr,
        )
        return 1

    # --- Core: parse + fetch, no web layer ---------------------------------------------------
    reference, text = fetch_verse_in_process(args.db, args.ref, args.translation)
    print(f"Parsed {args.ref!r} -> {reference.echo}  (book {reference.book_id})")
    if text is None:
        print(f"  {args.translation.upper()} has no text for {reference.echo}.")
    else:
        print(f"  {args.translation.upper()}: {text}")

    # --- Optional: semantic search (needs the model + vector store) --------------------------
    results = semantic_search_in_process(args.db, args.query)
    if results is None:
        print(
            "\nSemantic search skipped: bible_semantic, the embedding model, or the vector "
            "store isn't available.\n"
            "  (fetch the model with scripts/fetch_model.py and build embeddings to enable it.)"
        )
    else:
        print(f"\nSemantic search for {args.query!r} (top {len(results)}):")
        for ref, score, verse_text in results:
            print(f"  {ref:<12} {score:.4f}  {verse_text}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
