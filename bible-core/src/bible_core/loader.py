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

# (translation_id, book_id, chapter, before_verse, ordinal, text)
HeadingRow = tuple[str, str, int, int, int, str]


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
    headings: list[HeadingRow]


@dataclass(frozen=True)
class BuildStats:
    """Summary of a completed build."""

    translations: int
    verses: int
    books_with_verses: int
    cross_references: int
    cross_refs_clamped: int
    places: int
    place_verses: int
    places_excluded: int
    place_verse_links_skipped: int
    notes: int
    note_cross_references: int
    section_headings: int
    topics: int
    topic_verses: int
    strongs_entries: int
    word_tokens: int
    elapsed_seconds: float


# (from_book_id, from_chapter, from_verse, to_book_id, to_chapter,
#  to_verse_start, to_verse_end, votes)
CrossRefDbRow = tuple[str, int, int, str, int, int, int | None, int]


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


def _opt_list(obj: Any, key: str, ctx: str) -> list[Any]:
    """A list field that may be absent or null (→ empty). Used for optional `headings`."""
    if not isinstance(obj, dict):
        raise LoaderError(f"{ctx}: expected a JSON object, got {type(obj).__name__}.")
    value = cast("dict[str, Any]", obj).get(key)
    if value is None:
        return []
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

    # Optional reading direction (RTL for Hebrew); defaults to ltr when absent. (`raw` is a dict —
    # the required-field reads above would have raised otherwise.)
    direction = raw.get("direction", DEFAULT_DIRECTION)
    if direction not in ("ltr", "rtl"):
        raise LoaderError(f"{path.name}: 'direction' must be 'ltr' or 'rtl', got {direction!r}.")

    rows: list[VerseRow] = []
    heading_rows: list[HeadingRow] = []
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

            # Section headings already live in the chapter dict; bake them (was discarded).
            # `ordinal` = 1-based source array order, so a chapter's headings stay stable.
            for h_ordinal, heading in enumerate(_opt_list(chapter, "headings", ch_ctx), start=1):
                h_ctx = f"{ch_ctx} headings[{h_ordinal - 1}]"
                before_verse = _get_int(heading, "before_verse", h_ctx)
                heading_text = _get_str(heading, "text", h_ctx).strip()
                if not heading_text:
                    raise LoaderError(f"{h_ctx}: 'text' is empty.")
                heading_rows.append(
                    (code, book_id, chapter_number, before_verse, h_ordinal, heading_text)
                )

    return TranslationData(
        id=code,
        name=name,
        language=language,
        direction=direction,
        versification=DEFAULT_VERSIFICATION,
        attribution=attribution,
        verses=rows,
        headings=heading_rows,
    )


# --- cross-references (openbible.info TSV: From Verse / To Verse / Votes) -------------


def _parse_xref_verse(token: str, alias_to_book: dict[str, str], ctx: str) -> tuple[str, int, int]:
    """Parse a ``Book.Chapter.Verse`` token (e.g. ``1Cor.8.6``) to ``(book_id, ch, v)``."""
    parts = token.split(".")
    if len(parts) != 3:
        raise LoaderError(f"{ctx}: malformed verse {token!r} (expected Book.Chapter.Verse).")
    book_token, chapter_text, verse_text = parts
    book_id = alias_to_book.get(normalize(book_token))
    if book_id is None:
        raise LoaderError(
            f"{ctx}: book {book_token!r} in {token!r} does not resolve to a known book."
        )
    try:
        chapter, verse = int(chapter_text), int(verse_text)
    except ValueError as exc:
        raise LoaderError(f"{ctx}: non-integer chapter/verse in {token!r}.") from exc
    if chapter < 1 or verse < 1:
        raise LoaderError(f"{ctx}: chapter and verse must be positive in {token!r}.")
    return book_id, chapter, verse


def parse_cross_reference_file(
    path: Path, alias_to_book: dict[str, str]
) -> tuple[list[CrossRefDbRow], int]:
    """Parse one cross-reference TSV file. Returns (rows, clamped_count).

    The first line is the header. ``From`` is a single verse; ``To`` is a single verse or
    a ``A-B`` range. A target range that crosses a chapter or book boundary cannot be held
    by the schema's single ``to_chapter``, so it is **clamped to its start verse**
    (``to_verse_end = NULL``) and counted.
    """
    rows: list[CrossRefDbRow] = []
    clamped = 0
    with path.open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if line_no == 1:  # header row
                continue
            line = raw_line.rstrip("\n")
            if not line:
                continue
            ctx = f"{path.name}:{line_no}"
            fields = line.split("\t")
            if len(fields) != 3:
                raise LoaderError(f"{ctx}: expected 3 tab-separated columns, found {len(fields)}.")
            from_field, to_field, votes_field = fields
            from_book, from_ch, from_v = _parse_xref_verse(from_field, alias_to_book, ctx)

            to_end: int | None
            if "-" in to_field:
                left, right = to_field.split("-", 1)
                to_book, to_ch, to_start = _parse_xref_verse(left, alias_to_book, ctx)
                end_book, end_ch, end_v = _parse_xref_verse(right, alias_to_book, ctx)
                if end_book == to_book and end_ch == to_ch:
                    to_end = end_v
                else:  # cross-chapter / cross-book range → clamp to the start verse
                    to_end = None
                    clamped += 1
            else:
                to_book, to_ch, to_start = _parse_xref_verse(to_field, alias_to_book, ctx)
                to_end = None

            try:
                votes = int(votes_field)
            except ValueError as exc:
                raise LoaderError(f"{ctx}: non-integer votes {votes_field!r}.") from exc

            rows.append((from_book, from_ch, from_v, to_book, to_ch, to_start, to_end, votes))
    return rows, clamped


def discover_cross_ref_files(cross_ref_dirs: list[Path]) -> list[Path]:
    """Return every regular (non-hidden) file under the given dirs, deterministically."""
    files: list[Path] = []
    for directory in cross_ref_dirs:
        if directory.is_dir():
            files.extend(
                p for p in directory.glob("*") if p.is_file() and not p.name.startswith(".")
            )
    return sorted(files, key=lambda p: str(p))


def load_cross_references(
    conn: sqlite3.Connection, cross_ref_dirs: list[Path], alias_to_book: dict[str, str]
) -> tuple[int, int]:
    """Insert cross-references from the given dirs. Returns (inserted, clamped)."""
    rows: list[CrossRefDbRow] = []
    clamped_total = 0
    for path in discover_cross_ref_files(cross_ref_dirs):
        file_rows, clamped = parse_cross_reference_file(path, alias_to_book)
        rows.extend(file_rows)
        clamped_total += clamped
    conn.executemany(
        "INSERT INTO cross_references "
        "(from_book_id, from_chapter, from_verse, to_book_id, to_chapter, "
        "to_verse_start, to_verse_end, votes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows), clamped_total


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


def build_database(
    db_path: Path,
    data_dirs: list[Path],
    cross_ref_dirs: list[Path] | None = None,
    geo_dir: Path | None = None,
    notes_dirs: list[Path] | None = None,
    topics_dir: Path | None = None,
    lexicon_dir: Path | None = None,
    tokens_dir: Path | None = None,
) -> BuildStats:
    """Build a complete ``bible.db`` from the data under ``data_dirs`` (translations),
    ``cross_ref_dirs`` (cross-reference TSV), ``geo_dir`` (geography JSONL), ``notes_dirs``
    (translator's-notes JSON), and ``topics_dir`` (topical-Bible JSON). Idempotent — same
    inputs, byte-identical db.

    ``notes_dirs`` is normally ``[data/notes, data/private/notes]`` (ADR-0004): the first is the
    committed public-domain notes that ship in the image; the second holds user-supplied,
    non-redistributable notes and is gitignored + dockerignored, so a clean build bakes zero
    private notes. Both are scanned non-recursively and are separate from the translation scan
    (``data_dirs``) so a notes file is never mistaken for a translation. Absent/empty dirs load
    nothing — not an error."""
    start = time.perf_counter()
    cross_ref_dirs = cross_ref_dirs or []
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
        heading_total = 0
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
                conn.executemany(
                    "INSERT INTO section_headings "
                    "(translation_id, book_id, chapter, before_verse, ordinal, text) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    t.headings,
                )
                heading_total += len(t.headings)
            conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")
            _update_chapter_counts(conn)
            cross_ref_count, cross_refs_clamped = load_cross_references(
                conn, cross_ref_dirs, alias_to_book
            )
            # Local import breaks the loader↔geo import cycle: geo.py imports LoaderError from
            # this module, so this module must not import geo at top level.
            from .geo import GeoStats, load_places

            geo_stats = (
                load_places(conn, geo_dir, order_to_book, alias_to_book)
                if geo_dir is not None
                else GeoStats(0, 0, 0, 0, {})
            )

            # Notes loader — same local-import cycle break as geo (notes.py imports LoaderError).
            from .notes import NotesStats, load_notes

            notes_stats = (
                load_notes(conn, notes_dirs, frozenset(seen_codes), alias_to_book)
                if notes_dirs is not None
                else NotesStats(0, 0, {})
            )

            # Topics loader — same local-import cycle break (topics.py imports LoaderError).
            from .topics import TopicsStats, load_topics

            topics_stats = (
                load_topics(conn, topics_dir, alias_to_book)
                if topics_dir is not None
                else TopicsStats(0, 0, 0, 0)
            )

            # Strong's-lexicon + word-tokens loaders — same local-import cycle break.
            from .strongs import (
                StrongsStats,
                WordTokensStats,
                load_strongs_entries,
                load_word_tokens,
            )

            strongs_stats = (
                load_strongs_entries(conn, lexicon_dir)
                if lexicon_dir is not None
                else StrongsStats(0)
            )
            tokens_stats = (
                load_word_tokens(conn, tokens_dir, alias_to_book)
                if tokens_dir is not None
                else WordTokensStats(0, 0)
            )

        books_with_verses = conn.execute(
            "SELECT COUNT(*) FROM books WHERE chapter_count IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()

    return BuildStats(
        translations=len(translations),
        verses=verse_total,
        books_with_verses=books_with_verses,
        cross_references=cross_ref_count,
        cross_refs_clamped=cross_refs_clamped,
        places=geo_stats.places,
        place_verses=geo_stats.place_verses,
        places_excluded=geo_stats.places_excluded,
        place_verse_links_skipped=geo_stats.verse_links_skipped,
        notes=notes_stats.notes,
        note_cross_references=notes_stats.note_cross_references,
        section_headings=heading_total,
        topics=topics_stats.topics,
        topic_verses=topics_stats.topic_verses,
        strongs_entries=strongs_stats.strongs_entries,
        word_tokens=tokens_stats.word_tokens,
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

    base = Path(args.data_dir)
    data_dirs = _default_data_dirs(base)
    cross_ref_dirs = [base / "cross-references"]
    geo_dir = base / "geography"
    # Two notes paths (ADR-0004), scanned in order: committed public-domain notes that ship
    # (`data/notes/`), then user-supplied non-redistributable notes (`data/private/notes/`).
    # The latter is dual-ignored, so the public build has no `private/` and bakes zero private
    # notes — only the committed public ones.
    notes_dirs = [base / "notes", base / "private" / "notes"]
    # Committed topical-Bible dataset (Nave's, CC BY 4.0) — ships in the image like geography.
    topics_dir = base / "topics"
    # Committed Strong's lexicon + tagged word tokens (STEPBible, CC BY 4.0), both under
    # data/strongs/; the lexicon loader reads lexicon*.json, the token loader reads tokens-*.json.
    lexicon_dir = base / "strongs"
    tokens_dir = base / "strongs"
    try:
        stats = build_database(
            Path(args.output),
            data_dirs,
            cross_ref_dirs,
            geo_dir,
            notes_dirs,
            topics_dir,
            lexicon_dir,
            tokens_dir,
        )
    except LoaderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        clamped = (
            f" ({stats.cross_refs_clamped} multi-chapter targets clamped to start)"
            if stats.cross_refs_clamped
            else ""
        )
        print(
            f"Built {args.output}: {stats.translations} translations, "
            f"{stats.verses} verses, {stats.books_with_verses} books, "
            f"{stats.cross_references} cross-references{clamped}, "
            f"{stats.places} places, {stats.place_verses} place-verse links, "
            f"{stats.notes} notes, {stats.note_cross_references} note cross-references, "
            f"{stats.section_headings} section headings, "
            f"{stats.topics} topics, {stats.topic_verses} topic-verse links, "
            f"{stats.strongs_entries} Strong's entries, {stats.word_tokens} word tokens "
            f"in {stats.elapsed_seconds:.2f}s."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
