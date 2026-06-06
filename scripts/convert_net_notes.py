"""Reshape a soap-journal translation file's embedded footnotes into Concord's v4 notes JSON.

soap-journal ships notes as `footnotes[]` nested under `books[].chapters[]` inside the
translation file; Concord's loader (`bible_core.notes`) wants a flat
`{"translation": "<CODE>", "notes": [...]}` at `data/private/notes/<CODE>.json`. The field
*vocabulary* already matches (Concord's SPEC §4 mirrored soap-journal), so this is a mechanical
reshape — flatten, inject the book/chapter anchor, rename a few fields, stringify the marker, and
map cross-ref `to_book_order_index` → a book token.

Read-only of the input; writes only the output file. Run locally on data you legally own — the
output lives under the gitignored/dockerignored `data/private/` and is never committed or shipped.

    # default: data/private/net.json -> data/private/notes/NET.json
    python scripts/convert_net_notes.py
    python scripts/convert_net_notes.py --input X --output Y
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def convert(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Return (Concord notes payload, stats). Skips-and-counts malformed entries so the emitted
    file is guaranteed loadable; nothing is silently dropped."""
    code: str = raw["code"]
    books: list[dict[str, Any]] = raw["books"]
    # order_index -> book token (the book's own abbreviation, which Concord resolves via aliases).
    order_to_abbr: dict[int, str] = {b["order_index"]: b["abbreviation"] for b in books}

    notes: list[dict[str, Any]] = []
    stats: dict[str, int] = {
        "notes": 0,
        "cross_refs": 0,
        "skipped_empty_text": 0,
        "skipped_bad_verse": 0,
        "skipped_xref_unknown_book": 0,
    }

    for book in books:
        abbr: str = book["abbreviation"]
        chapters: list[dict[str, Any]] = book["chapters"]
        for chapter in chapters:
            ch_num: int = chapter["number"]
            footnotes: list[dict[str, Any]] = chapter.get("footnotes") or []
            for fn in footnotes:
                verse = fn.get("verse_number")
                text = (fn.get("text") or "").strip()
                if not isinstance(verse, int) or verse < 1:
                    stats["skipped_bad_verse"] += 1
                    continue
                if not text:
                    stats["skipped_empty_text"] += 1
                    continue

                cross_references: list[dict[str, Any]] = []
                cross_refs: list[dict[str, Any]] = fn.get("cross_refs") or []
                for x in cross_refs:
                    order_key: Any = x.get("to_book_order_index")
                    to_book = order_to_abbr.get(order_key)
                    if to_book is None:
                        stats["skipped_xref_unknown_book"] += 1
                        continue
                    cross_references.append(
                        {
                            "book": to_book,
                            "chapter": x["to_chapter"],
                            "verse_start": x["to_verse_start"],
                            "verse_end": x["to_verse_end"],
                        }
                    )

                marker = fn.get("marker")
                note: dict[str, Any] = {
                    "book": abbr,
                    "chapter": ch_num,
                    "verse": verse,
                    "text": text,
                    "type": fn.get("note_type"),
                    "char_offset": fn.get("char_offset", 0),
                    "marker": None if marker is None else str(marker),
                    "ordinal": fn.get("ordinal"),
                    "cross_references": cross_references,
                }
                notes.append(note)
                stats["notes"] += 1
                stats["cross_refs"] += len(cross_references)

    return {"translation": code, "notes": notes}, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/private/net.json", type=Path)
    parser.add_argument("--output", default="data/private/notes/NET.json", type=Path)
    args = parser.parse_args(argv)

    raw: dict[str, Any] = json.loads(args.input.read_text(encoding="utf-8"))
    payload, stats = convert(raw)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print(
        f"Wrote {args.output}: translation={payload['translation']!r}, "
        f"{stats['notes']} notes, {stats['cross_refs']} note cross-references."
    )
    skipped = {k: v for k, v in stats.items() if k.startswith("skipped_") and v}
    if skipped:
        print(f"  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
