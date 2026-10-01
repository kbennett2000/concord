"""The verse skeleton every parse is checked against, and the NLT's known departures from it.

The skeleton is the committed public-domain KJV (31,102 verses), read at run time. The NLT
follows it except where it omits a verse that most modern translations relegate to a footnote,
and in two places where its versification adds a verse. Combined verses (a size-7 "20-21") are
found in the PDF itself, not listed here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from emb_convert.layout import canonical_books

Key = tuple[str, int, int]

REPO_ROOT = Path(__file__).resolve().parents[2]
SKELETON_FILE = REPO_ROOT / "data" / "translations" / "KJV.json"

NLT_OMITTED: frozenset[Key] = frozenset(
    {
        ("MAT", 17, 21),
        ("MAT", 18, 11),
        ("MAT", 23, 14),
        ("MRK", 7, 16),
        ("MRK", 9, 44),
        ("MRK", 9, 46),
        ("MRK", 11, 26),
        ("MRK", 15, 28),
        ("LUK", 17, 36),
        ("LUK", 23, 17),
        ("JHN", 5, 4),
        ("ACT", 8, 37),
        ("ACT", 15, 34),
        ("ACT", 24, 7),
        ("ACT", 28, 29),
        ("ROM", 16, 24),
    }
)
NLT_EXTRA: frozenset[Key] = frozenset({("3JN", 1, 15), ("REV", 12, 18)})


def load_skeleton(path: Path = SKELETON_FILE) -> dict[tuple[str, int], int]:
    """(book, chapter) → verse count, from the committed KJV."""
    order_to_code = {seed.canonical_order: seed.id for seed in canonical_books()}
    raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    counts: dict[tuple[str, int], int] = {}
    for book in cast(list[dict[str, Any]], raw["books"]):
        code = order_to_code[int(book["order_index"])]
        for chapter in cast(list[dict[str, Any]], book["chapters"]):
            verses = cast(list[dict[str, Any]], chapter["verses"])
            counts[(code, int(chapter["number"]))] = len(verses)
    return counts


def load_verses(path: Path) -> dict[Key, str]:
    """A translation file's verse texts by (book, chapter, verse) — the cross-check's NLT."""
    order_to_code = {seed.canonical_order: seed.id for seed in canonical_books()}
    raw = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    verses: dict[Key, str] = {}
    for book in cast(list[dict[str, Any]], raw["books"]):
        code = order_to_code[int(book["order_index"])]
        for chapter in cast(list[dict[str, Any]], book["chapters"]):
            for verse in cast(list[dict[str, Any]], chapter["verses"]):
                verses[(code, int(chapter["number"]), int(verse["number"]))] = str(verse["text"])
    return verses


PUBLIC_VOCABULARY = ("WEB", "KJV", "BSB", "ASV")


def load_public_texts(directory: Path = REPO_ROOT / "data" / "translations") -> list[str]:
    """Verse texts of the committed public-domain English translations (a word list)."""
    texts: list[str] = []
    for code in PUBLIC_VOCABULARY:
        raw = cast(dict[str, Any], json.loads((directory / f"{code}.json").read_text("utf-8")))
        for book in cast(list[dict[str, Any]], raw["books"]):
            for chapter in cast(list[dict[str, Any]], book["chapters"]):
                texts.extend(str(v["text"]) for v in cast(list[dict[str, Any]], chapter["verses"]))
    return texts
