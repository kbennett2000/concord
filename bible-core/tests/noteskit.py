"""Builders for synthetic translator's-notes JSON used by the notes loader tests.

Keeps the unit suite fast, fully controlled, and — crucially — **licensing-clean**: the
fixtures are a handful of fake notes in the real JSON shape, never the copyrighted NET data
(SPEC v4 §11). Book tokens use real abbreviations so they resolve through the seeded aliases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def note_xref(
    book: str, chapter: int, verse_start: int, verse_end: int | None = None
) -> dict[str, Any]:
    return {
        "book": book,
        "chapter": chapter,
        "verse_start": verse_start,
        "verse_end": verse_end,
    }


def note_passage(
    start_chapter: int, start_verse: int, end_chapter: int, end_verse: int
) -> dict[str, Any]:
    return {
        "start_chapter": start_chapter,
        "start_verse": start_verse,
        "end_chapter": end_chapter,
        "end_verse": end_verse,
    }


def note(
    book: str,
    chapter: int,
    verse: int,
    text: str,
    *,
    type: str | None = None,
    char_offset: int | None = None,
    marker: str | None = None,
    ordinal: int | None = None,
    cross_references: list[dict[str, Any]] | None = None,
    label: str | None = None,
    title: str | None = None,
    text_format: str | None = None,
    passages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One note in the input shape. Optional fields are omitted when None, so the loader's
    defaulting (NULL type, char_offset 0, per-verse ordinal, no v8 fields) is exercised."""
    payload: dict[str, Any] = {"book": book, "chapter": chapter, "verse": verse, "text": text}
    if type is not None:
        payload["type"] = type
    if char_offset is not None:
        payload["char_offset"] = char_offset
    if marker is not None:
        payload["marker"] = marker
    if ordinal is not None:
        payload["ordinal"] = ordinal
    if cross_references is not None:
        payload["cross_references"] = cross_references
    optional = {"label": label, "title": title, "text_format": text_format, "passages": passages}
    payload.update({k: v for k, v in optional.items() if v is not None})
    return payload


def notes_file(translation: str, notes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"translation": translation, "notes": notes}


def write_notes(directory: Path, payload: dict[str, Any], *, filename: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (filename or f"{payload['translation']}.json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
