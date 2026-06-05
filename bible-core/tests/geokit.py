"""Builders for synthetic OpenBible geography JSONL used by the geo-loader tests.

Keeps the unit suite fast and fully controlled (no dependence on the 14 MB real files).
Mirrors only the subset of the ancient/modern structure that ``bible_core.geo`` reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def modern_loc(modern_id: str, longitude: float, latitude: float) -> dict[str, Any]:
    """A modern.jsonl record. ``lonlat`` is "longitude,latitude" order (longitude first)."""
    return {"id": modern_id, "lonlat": f"{longitude},{latitude}"}


def assoc(score: int, name: str) -> dict[str, Any]:
    """One ``modern_associations`` value (keyed by modern id in the place record)."""
    return {"score": score, "name": name, "url_slug": name.lower().replace(" ", "-")}


def verse_ref(
    book_order: int, chapter: int, verse: int, *, osis: str | None = None
) -> dict[str, Any]:
    """A ``verses[]`` entry. ``sort`` is BBCCCVVV; ``osis`` optional for the fallback path."""
    entry: dict[str, Any] = {"sort": f"{book_order:02d}{chapter:03d}{verse:03d}"}
    if osis is not None:
        entry["osis"] = osis
    return entry


def osis_only_verse(osis: str) -> dict[str, Any]:
    """A ``verses[]`` entry with no ``sort`` — exercises the osis fallback."""
    return {"osis": osis}


def ancient_place(
    place_id: str,
    friendly_id: str,
    *,
    types: tuple[str, ...] = ("settlement",),
    article: str = "",
    associations: dict[str, dict[str, Any]] | None = None,
    specials: tuple[str, ...] = (),
    verses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """An ancient.jsonl record. ``specials`` are nested as resolution markers; top-level
    ``name``/``type`` are left absent (null), matching the real data."""
    record: dict[str, Any] = {
        "id": place_id,
        "friendly_id": friendly_id,
        "url_slug": friendly_id.lower().replace(" ", "-"),
        "preceding_article": article,
        "types": list(types),
        "modern_associations": associations or {},
        "verses": verses or [],
    }
    if specials:
        record["identifications"] = [
            {"resolutions": [{"special": special} for special in specials]}
        ]
    return record


def write_geo(
    directory: Path,
    ancient_records: list[dict[str, Any]],
    modern_records: list[dict[str, Any]],
) -> Path:
    """Write ancient.jsonl + modern.jsonl into ``directory`` and return it."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ancient.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in ancient_records), encoding="utf-8"
    )
    (directory / "modern.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in modern_records), encoding="utf-8"
    )
    return directory
