"""Builders for synthetic translation JSON used by the loader tests.

Keeps the unit suite fast and fully controlled (no dependence on the large real files).
Abbreviations/order_index use real values so they resolve through the seeded aliases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def verse(number: int, text: str) -> dict[str, Any]:
    return {"number": number, "text": text, "is_red_letter": False}


def heading(before_verse: int, text: str) -> dict[str, Any]:
    return {"before_verse": before_verse, "text": text}


def chapter(
    number: int,
    verses: list[dict[str, Any]],
    headings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "verses": verses,
        "headings": headings or [],
        "footnotes": [],
    }


def book(abbreviation: str, order_index: int, chapters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "abbreviation": abbreviation,
        "name": abbreviation,
        "order_index": order_index,
        "chapters": chapters,
    }


def translation(
    code: str,
    books: list[dict[str, Any]],
    *,
    name: str = "Test Version",
    language: str = "en",
    attribution: str = "Public domain.",
) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "language": language,
        "copyright": attribution,
        "books": books,
    }


def write_translation(
    directory: Path, payload: dict[str, Any], *, filename: str | None = None
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (filename or f"{payload['code']}.json")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
