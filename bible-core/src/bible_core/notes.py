"""Build-time translator's-notes loader — ingest of notes JSON (SPEC v4, ADR-0004).

Reads notes JSON from one or more notes directories (one file per translation) and populates
the additive ``translator_notes`` + ``note_cross_references`` tables, then rebuilds the
``notes_fts`` index. The v4 analogue of the cross-reference / geography loaders: a build-time,
idempotent data load baked into ``bible.db``.

**Two pickup paths (ADR-0004).** Notes are loaded from a *list* of directories, scanned in
order and unioned:

- ``data/notes/`` — **committed, public-domain** notes that *ship* in the image (e.g. the WEB
  translation's own PD footnotes). Not gitignored, not dockerignored.
- ``data/private/notes/`` — **user-supplied, non-redistributable** notes (e.g. NET). Under the
  gitignored + dockerignored ``data/private/`` tree, so it never reaches the published image.

**Licensing (SPEC v4 §2-§3, ADR-0004).** The dual-ignore rule still holds for ``data/private/``:
a clean build (no private data) bakes **zero private notes** — only the committed public notes.
Each notes directory is scanned non-recursively (``*.json``) and is separate from the top-level
translation scan, so a notes file is never mistaken for a translation. When the same translation
carries notes in more than one directory, both load (union, in directory order).

**Input contract (per notes JSON file).** One file describes one translation's notes::

    {
      "translation": "NET",                 # must match a loaded translation id
      "notes": [
        {
          "book": "JHN", "chapter": 3, "verse": 16,   # canonical anchor (book is an alias)
          "type": "tn",                     # optional: tn|sn|tc|map|other (NULL if omitted)
          "text": "The Greek reads ...",    # required, non-empty
          "char_offset": 12,                # optional point anchor (>= 0, default 0)
          "marker": "1",                    # optional source marker
          "ordinal": 1,                     # optional render order (default: per-verse seq)
          "cross_references": [             # optional
            {"book": "ROM", "chapter": 8, "verse_start": 1, "verse_end": null}
          ]
        }
      ]
    }

Note ids are assigned deterministically (files in sorted-path order, notes in array order),
so the same inputs yield a byte-identical database. Pure stdlib (``json`` + ``sqlite3``) —
``bible-core`` stays web-free and ML-free.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .loader import LoaderError
from .normalize import normalize

# The constrained note-type set (mirrors the schema CHECK). ``None`` (field omitted) is also
# valid — a plain footnote with no classification.
NOTE_TYPES: frozenset[str] = frozenset({"tn", "sn", "tc", "map", "other"})

# (id, translation_id, book_id, chapter, verse, note_type, text, char_offset, marker, ordinal)
NoteRow = tuple[int, str, str, int, int, str | None, str, int, str | None, int]
# (note_id, to_book_id, to_chapter, to_verse_start, to_verse_end)
NoteXrefRow = tuple[int, str, int, int, int | None]


@dataclass(frozen=True)
class NotesStats:
    """Summary of a completed notes load."""

    notes: int
    note_cross_references: int
    by_type: dict[str, int]


# --- JSON extraction helpers (validate + narrow types, with actionable errors) -------


def _get(obj: Any, key: str, ctx: str) -> Any:
    if not isinstance(obj, dict):
        raise LoaderError(f"{ctx}: expected a JSON object, got {type(obj).__name__}.")
    mapping = cast("dict[str, Any]", obj)
    if key not in mapping:
        raise LoaderError(f"{ctx}: missing required field {key!r}.")
    return mapping[key]


def _req_str(obj: Any, key: str, ctx: str) -> str:
    value = _get(obj, key, ctx)
    if not isinstance(value, str):
        raise LoaderError(f"{ctx}: field {key!r} must be a string, got {type(value).__name__}.")
    return value


def _req_int(obj: Any, key: str, ctx: str) -> int:
    value = _get(obj, key, ctx)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoaderError(f"{ctx}: field {key!r} must be an integer, got {type(value).__name__}.")
    return value


def _req_list(obj: Any, key: str, ctx: str) -> list[Any]:
    value = _get(obj, key, ctx)
    if not isinstance(value, list):
        raise LoaderError(f"{ctx}: field {key!r} must be a list, got {type(value).__name__}.")
    return cast("list[Any]", value)


def _opt_int(obj: dict[str, Any], key: str, default: int, ctx: str) -> int:
    if key not in obj or obj[key] is None:
        return default
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoaderError(f"{ctx}: field {key!r} must be an integer, got {type(value).__name__}.")
    return value


def _opt_str(obj: dict[str, Any], key: str, ctx: str) -> str | None:
    if key not in obj or obj[key] is None:
        return None
    value = obj[key]
    if not isinstance(value, str):
        raise LoaderError(f"{ctx}: field {key!r} must be a string, got {type(value).__name__}.")
    return value


def _opt_list(obj: dict[str, Any], key: str, ctx: str) -> list[Any]:
    if key not in obj or obj[key] is None:
        return []
    value = obj[key]
    if not isinstance(value, list):
        raise LoaderError(f"{ctx}: field {key!r} must be a list, got {type(value).__name__}.")
    return cast("list[Any]", value)


# --- parsing -------------------------------------------------------------------------


def _resolve_book(token: str, alias_to_book: dict[str, str], ctx: str) -> str:
    book_id = alias_to_book.get(normalize(token))
    if book_id is None:
        raise LoaderError(f"{ctx}: book {token!r} does not resolve to a known book.")
    return book_id


def _parse_cross_reference(
    raw: Any, note_id: int, alias_to_book: dict[str, str], ctx: str
) -> NoteXrefRow:
    to_book_id = _resolve_book(_req_str(raw, "book", ctx), alias_to_book, ctx)
    to_chapter = _req_int(raw, "chapter", ctx)
    to_verse_start = _req_int(raw, "verse_start", ctx)
    to_verse_end = _opt_int(cast("dict[str, Any]", raw), "verse_end", -1, ctx)
    end: int | None = None if to_verse_end < 0 else to_verse_end
    if to_chapter < 1 or to_verse_start < 1:
        raise LoaderError(f"{ctx}: chapter and verse_start must be positive.")
    if end is not None and end < to_verse_start:
        raise LoaderError(f"{ctx}: verse_end {end} is before verse_start {to_verse_start}.")
    return (note_id, to_book_id, to_chapter, to_verse_start, end)


def parse_notes_file(
    path: Path,
    next_id: int,
    translation_ids: frozenset[str],
    alias_to_book: dict[str, str],
) -> tuple[list[NoteRow], list[NoteXrefRow]]:
    """Parse one notes JSON file into note rows + cross-ref rows.

    Note ids are assigned from ``next_id`` upward, in array order, so the build is
    reproducible. Structural violations fail loudly with ``LoaderError``.
    """
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path.name}: invalid JSON ({exc}).") from exc

    translation_id = _req_str(raw, "translation", path.name)
    if translation_id not in translation_ids:
        known = ", ".join(sorted(translation_ids)) or "(none loaded)"
        raise LoaderError(
            f"{path.name}: notes reference translation {translation_id!r}, which is not a "
            f"loaded translation. Known translations: {known}."
        )

    note_rows: list[NoteRow] = []
    xref_rows: list[NoteXrefRow] = []
    # Per-verse running counter for the default `ordinal` (stable render order).
    seq: Counter[tuple[str, int, int]] = Counter()
    note_id = next_id
    for index, note in enumerate(_req_list(raw, "notes", path.name)):
        ctx = f"{path.name} notes[{index}]"
        book_id = _resolve_book(_req_str(note, "book", ctx), alias_to_book, ctx)
        chapter = _req_int(note, "chapter", ctx)
        verse = _req_int(note, "verse", ctx)
        if chapter < 1 or verse < 1:
            raise LoaderError(f"{ctx}: chapter and verse must be positive.")
        text = _req_str(note, "text", ctx).strip()
        if not text:
            raise LoaderError(f"{ctx}: 'text' is empty.")
        note_type = _opt_str(cast("dict[str, Any]", note), "type", ctx)
        if note_type is not None and note_type not in NOTE_TYPES:
            allowed = ", ".join(sorted(NOTE_TYPES))
            raise LoaderError(
                f"{ctx}: unknown note type {note_type!r} (expected one of {allowed})."
            )
        char_offset = _opt_int(cast("dict[str, Any]", note), "char_offset", 0, ctx)
        if char_offset < 0:
            raise LoaderError(f"{ctx}: 'char_offset' must be >= 0.")
        marker = _opt_str(cast("dict[str, Any]", note), "marker", ctx)

        seq[(book_id, chapter, verse)] += 1
        ordinal = _opt_int(
            cast("dict[str, Any]", note), "ordinal", seq[(book_id, chapter, verse)], ctx
        )

        note_rows.append(
            (
                note_id,
                translation_id,
                book_id,
                chapter,
                verse,
                note_type,
                text,
                char_offset,
                marker,
                ordinal,
            )
        )

        for xi, xref in enumerate(_opt_list(cast("dict[str, Any]", note), "cross_references", ctx)):
            xref_rows.append(
                _parse_cross_reference(
                    xref, note_id, alias_to_book, f"{ctx} cross_references[{xi}]"
                )
            )
        note_id += 1

    return note_rows, xref_rows


# --- discovery + load ----------------------------------------------------------------


def discover_notes_files(notes_dir: Path) -> list[Path]:
    """Return every ``*.json`` directly under ``notes_dir``, in deterministic order."""
    if not notes_dir.is_dir():
        return []
    return sorted(notes_dir.glob("*.json"), key=lambda p: str(p))


def discover_notes_files_in_dirs(notes_dirs: list[Path]) -> list[Path]:
    """Return notes files across all ``notes_dirs``, in a deterministic union order.

    Directories are scanned in the given order (public before private); within each, files
    are sorted by path. The fixed dir order keeps note-id assignment reproducible even when
    the same translation appears in more than one directory."""
    files: list[Path] = []
    for notes_dir in notes_dirs:
        files.extend(discover_notes_files(notes_dir))
    return files


def load_notes(
    conn: sqlite3.Connection,
    notes_dirs: list[Path],
    translation_ids: frozenset[str],
    alias_to_book: dict[str, str],
) -> NotesStats:
    """Ingest notes JSON files from ``notes_dirs`` into ``translator_notes`` /
    ``note_cross_references`` and rebuild ``notes_fts``. Directories are scanned in order and
    unioned (ADR-0004). A missing/empty directory loads nothing (the public-image /
    clean-build case for ``data/private/notes/``) — not an error."""
    note_rows: list[NoteRow] = []
    xref_rows: list[NoteXrefRow] = []
    by_type: Counter[str] = Counter()
    next_id = 1
    for path in discover_notes_files_in_dirs(notes_dirs):
        notes, xrefs = parse_notes_file(path, next_id, translation_ids, alias_to_book)
        note_rows.extend(notes)
        xref_rows.extend(xrefs)
        next_id += len(notes)
        for row in notes:
            by_type[row[5] or "other"] += 1

    conn.executemany(
        "INSERT INTO translator_notes "
        "(id, translation_id, book_id, chapter, verse, note_type, text, char_offset, "
        "marker, ordinal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        note_rows,
    )
    conn.executemany(
        "INSERT INTO note_cross_references "
        "(note_id, to_book_id, to_chapter, to_verse_start, to_verse_end) "
        "VALUES (?, ?, ?, ?, ?)",
        xref_rows,
    )
    conn.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
    return NotesStats(
        notes=len(note_rows),
        note_cross_references=len(xref_rows),
        by_type=dict(by_type),
    )
