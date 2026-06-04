"""Reproducible JSON → SQLite loader.

Scans the data directories (the filesystem is the manifest — no hardcoded filenames),
validates each translation file against the discovered input contract, and builds a
complete ``bible.db``: ``translations`` + ``verses`` populated, the FTS5 index rebuilt,
and ``chapter_count`` computed from real verse data. Composes Slice 1: it runs
``create_schema`` then ``seed_books`` before loading translations, so a full build is one
cohesive operation.

Reproducible and idempotent: the database is deleted and rebuilt from scratch every run,
files are processed in a deterministic order, and SQLite embeds no timestamps — so the
same inputs always yield a byte-identical file.

Input contract (per translation JSON file):
- top level: ``code``, ``name``, ``language``, ``copyright``, ``books`` (list)
- book: ``abbreviation``, ``name``, ``order_index``, ``chapters`` (list)
- chapter: ``number`` (int), ``verses`` (list)
- verse: ``number`` (int), ``text`` (str)

``bible-core`` stays web-free and Pydantic-free: stdlib ``json`` + ``sqlite3`` +
``dataclasses`` only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .db import apply_load_pragmas, connect
from .normalize import normalize
from .schema import create_schema
from .seed import seed_books

# Absent from the JSON; shared v1 defaults (see SPEC §3 — cross-scheme mapping deferred).
DEFAULT_DIRECTION = "ltr"
DEFAULT_VERSIFICATION = "standard"

# (translation_id, book_id, chapter, verse, text)
VerseRow = tuple[str, str, int, int, str]


class LoaderError(Exception):
    """Raised when a translation file violates the input contract."""


@dataclass(frozen=True)
class TranslationData:
    """One parsed translation: metadata plus its prepared verse rows."""

    id: str
    name: str
    language: str
    direction: str
    versification: str
    attribution: str
    verses: list[VerseRow]


@dataclass(frozen=True)
class BuildStats:
    """Summary of a completed build."""

    translations: int
    verses: int
    books_with_verses: int
    elapsed_seconds: float


# --- JSON extraction helpers (validate + narrow types, with actionable errors) -------


def _get(obj: Any, key: str, ctx: str) -> Any:
    if not isinstance(obj, dict):
        raise LoaderError(f"{ctx}: expected a JSON object, got {type(obj).__name__}.")
    mapping = cast("dict[str, Any]", obj)
    if key not in mapping:
        raise LoaderError(f"{ctx}: missing required field {key!r}.")
    return mapping[key]


def _get_str(obj: Any, key: str, ctx: str) -> str:
    value = _get(obj, key, ctx)
    if not isinstance(value, str):
        raise LoaderError(f"{ctx}: field {key!r} must be a string, got {type(value).__name__}.")
    return value


def _get_int(obj: Any, key: str, ctx: str) -> int:
    value = _get(obj, key, ctx)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoaderError(f"{ctx}: field {key!r} must be an integer, got {type(value).__name__}.")
    return value


def _get_list(obj: Any, key: str, ctx: str) -> list[Any]:
    value = _get(obj, key, ctx)
    if not isinstance(value, list):
        raise LoaderError(f"{ctx}: field {key!r} must be a list, got {type(value).__name__}.")
    return cast("list[Any]", value)


# --- parsing -------------------------------------------------------------------------


def parse_translation_file(
    path: Path, alias_to_book: dict[str, str], order_to_book: dict[int, str]
) -> TranslationData:
    """Parse and validate one translation file into a ``TranslationData``."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path.name}: invalid JSON ({exc}).") from exc

    code = _get_str(raw, "code", path.name)
    name = _get_str(raw, "name", path.name)
    language = _get_str(raw, "language", path.name)
    attribution = _get_str(raw, "copyright", path.name)
    if not code:
        raise LoaderError(f"{path.name}: 'code' is empty.")

    rows: list[VerseRow] = []
    for book_index, book in enumerate(_get_list(raw, "books", path.name)):
        book_ctx = f"{path.name} books[{book_index}]"
        abbreviation = _get_str(book, "abbreviation", book_ctx)
        order_index = _get_int(book, "order_index", book_ctx)

        book_id = alias_to_book.get(normalize(abbreviation))
        if book_id is None:
            raise LoaderError(
                f"{book_ctx}: abbreviation {abbreviation!r} does not resolve to any "
                "seeded book alias."
            )
        expected = order_to_book.get(order_index)
        if expected != book_id:
            raise LoaderError(
                f"{book_ctx}: abbreviation {abbreviation!r} resolves to {book_id!r} but "
                f"order_index {order_index} maps to {expected!r} — inconsistent book identity."
            )

        for chapter in _get_list(book, "chapters", book_ctx):
            chapter_number = _get_int(chapter, "number", book_ctx)
            ch_ctx = f"{book_ctx} {book_id} ch.{chapter_number}"
            for verse in _get_list(chapter, "verses", ch_ctx):
                verse_number = _get_int(verse, "number", ch_ctx)
                text = _get_str(verse, "text", ch_ctx).strip()
                rows.append((code, book_id, chapter_number, verse_number, text))

    return TranslationData(
        id=code,
        name=name,
        language=language,
        direction=DEFAULT_DIRECTION,
        versification=DEFAULT_VERSIFICATION,
        attribution=attribution,
        verses=rows,
    )


# --- build ---------------------------------------------------------------------------


def discover_files(data_dirs: list[Path]) -> list[Path]:
    """Return every ``*.json`` under the given directories, in deterministic order."""
    files: list[Path] = []
    for directory in data_dirs:
        if directory.is_dir():
            files.extend(directory.glob("*.json"))
    return sorted(files, key=lambda p: str(p))


def _build_resolver(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[int, str]]:
    alias_to_book = {
        row[0]: row[1] for row in conn.execute("SELECT alias, book_id FROM book_aliases")
    }
    order_to_book = {
        row[0]: row[1] for row in conn.execute("SELECT canonical_order, id FROM books")
    }
    return alias_to_book, order_to_book


def _update_chapter_counts(conn: sqlite3.Connection) -> None:
    """Compute chapter_count per book; fail loudly if translations disagree."""
    per_book: dict[str, dict[str, int]] = defaultdict(dict)
    for book_id, translation_id, n_chapters in conn.execute(
        "SELECT book_id, translation_id, COUNT(DISTINCT chapter) "
        "FROM verses GROUP BY book_id, translation_id"
    ):
        per_book[book_id][translation_id] = n_chapters

    updates: list[tuple[int, str]] = []
    for book_id, by_translation in per_book.items():
        counts = set(by_translation.values())
        if len(counts) > 1:
            detail = ", ".join(f"{tid}={n}" for tid, n in sorted(by_translation.items()))
            raise LoaderError(
                f"Translations disagree on the chapter count for book {book_id!r}: {detail}. "
                "All translations must share chapter-level versification."
            )
        updates.append((counts.pop(), book_id))
    conn.executemany("UPDATE books SET chapter_count = ? WHERE id = ?", updates)


def build_database(db_path: Path, data_dirs: list[Path]) -> BuildStats:
    """Build a complete ``bible.db`` from the JSON under ``data_dirs``. Idempotent."""
    start = time.perf_counter()
    db_path.unlink(missing_ok=True)

    conn = connect(db_path)
    try:
        apply_load_pragmas(conn)
        create_schema(conn)
        seed_books(conn)
        alias_to_book, order_to_book = _build_resolver(conn)

        files = discover_files(data_dirs)
        if not files:
            raise LoaderError(
                f"No translation JSON found under: {', '.join(str(d) for d in data_dirs)}."
            )

        translations: list[TranslationData] = []
        seen_codes: dict[str, str] = {}
        for path in files:
            data = parse_translation_file(path, alias_to_book, order_to_book)
            if data.id in seen_codes:
                raise LoaderError(
                    f"Duplicate translation code {data.id!r} in {path.name} "
                    f"(already loaded from {seen_codes[data.id]})."
                )
            seen_codes[data.id] = path.name
            translations.append(data)

        verse_total = 0
        with conn:
            conn.executemany(
                "INSERT INTO translations "
                "(id, name, language, direction, versification, attribution) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (t.id, t.name, t.language, t.direction, t.versification, t.attribution)
                    for t in translations
                ],
            )
            for t in translations:
                conn.executemany(
                    "INSERT INTO verses (translation_id, book_id, chapter, verse, text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    t.verses,
                )
                verse_total += len(t.verses)
            conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")
            _update_chapter_counts(conn)

        books_with_verses = conn.execute(
            "SELECT COUNT(*) FROM books WHERE chapter_count IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()

    return BuildStats(
        translations=len(translations),
        verses=verse_total,
        books_with_verses=books_with_verses,
        elapsed_seconds=time.perf_counter() - start,
    )


# --- CLI -----------------------------------------------------------------------------


def _default_data_dirs(base: Path) -> list[Path]:
    """`<base>/translations` always; `<base>/private` only when it exists locally."""
    dirs = [base / "translations"]
    private = base / "private"
    if private.is_dir():
        dirs.append(private)
    return dirs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m bible_core.loader",
        description="Build bible.db from translation JSON (rebuilds from scratch).",
    )
    parser.add_argument(
        "-o", "--output", default="bible.db", help="output database path (default: bible.db)"
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="base data directory; scans its translations/ and private/ subdirs (default: data)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the summary line")
    args = parser.parse_args(argv)

    data_dirs = _default_data_dirs(Path(args.data_dir))
    try:
        stats = build_database(Path(args.output), data_dirs)
    except LoaderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(
            f"Built {args.output}: {stats.translations} translations, "
            f"{stats.verses} verses, {stats.books_with_verses} books "
            f"in {stats.elapsed_seconds:.2f}s."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
