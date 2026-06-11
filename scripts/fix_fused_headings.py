#!/usr/bin/env python3
"""One-shot cleanup for issue #67 — fused section headings in translation JSON.

An upstream extraction artifact fused each section heading onto the **last verse before
the new section** across the committed translations, leaving the heading text glued to the
end of a verse AND missing from that chapter's ``headings`` array. The fused text pollutes
the FTS search index and the WEB semantic embeddings (both read raw verse text).

This script restores clean Scripture: for every verse ending in a title-case "fused tail",
it strips the tail from the verse text and re-inserts it as a proper heading at
``before_verse = N + 1`` (a heading fused at verse N opens the section that starts at N+1).
A heading fused onto the last verse of a chapter opens the next chapter (``before_verse: 1``).

The files round-trip byte-identically through ``json.dumps(indent=2, ensure_ascii=False)``,
so the only diff is the cleaned verse-text lines plus the inserted heading objects. The run
is idempotent — a second pass finds nothing. A manifest of every change is written next to
this script so the low-confidence (single-translation) strips can be eyeballed in review.

    uv run python scripts/fix_fused_headings.py
    uv run python scripts/fix_fused_headings.py --dry-run   # detect + manifest, no writes

Original-language texts (OSHB, SBLGNT) carry no English headings and are untouched.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

# A fused tail is a title-case phrase trailing a sentence terminator at end of verse text.
# The terminator may be a period/?/! or a closing double OR single curly/straight quote
# (YLT/JPS close dialogue with ’). An optional stray verse number can sit between the
# terminator and the heading — this is how the artifact looks where the following verse is
# omitted (e.g. ASV Matt 17:20 carries "...you. 21 The Second Prediction of the Passion",
# verse 21 being a textual-variant verse absent from the critical text). The connective
# lowercase words keep multi-word headings ("The LORD Visits Sinai", "A Warning against
# Idolatry") intact while excluding ordinary prose continuations.
_CONNECTIVES = "of|the|and|to|in|a|against|before|from|for|over|with|into"
FUSED_TAIL = re.compile(
    r"[”’\"'.!?]\s+(?:(\d+)\s+)?"
    r"([A-Z][A-Za-z’']*(?:\s+(?:[A-Z][A-Za-z’']*|" + _CONNECTIVES + r"))*)$"
)

# Hebrew liturgical/musical notations that are verse *content* in the Psalms (e.g.
# "Higgaion Selah" in Ps 9:16), not section headings — a tail of only these is not fused.
NOTATION_WORDS = {"selah", "higgaion"}


class FusedMatch(NamedTuple):
    heading: str  # the section-heading text fused onto the verse
    cleaned: str  # the verse text with the fused tail (and any stray number) removed
    anchor: int | None  # stray verse number preceding the heading, if present


def fused_heading(text: str) -> FusedMatch | None:
    """Detect a section heading fused onto the end of ``text``; None if there is none.

    The heading must be at least two words and mostly capitalized — this excludes
    single-word proper-name endings (e.g. "...Ehud"), liturgical notations, and ordinary
    prose. ``cleaned`` keeps the verse's own terminator; ``anchor`` is the stray verse
    number between terminator and heading, if any.
    """
    stripped = text.rstrip()
    match = FUSED_TAIL.search(stripped)
    if not match:
        return None
    heading = match.group(2)
    words = heading.split()
    if len(words) < 2:
        return None
    capitalized = sum(1 for w in words if w[0].isupper())
    if capitalized < max(2, len(words) - 2):
        return None
    if all(w.strip(".,;'’").lower() in NOTATION_WORDS for w in words):
        return None
    cleaned = stripped[: match.start() + 1].rstrip()  # match.start() is the terminator char
    anchor = int(match.group(1)) if match.group(1) else None
    return FusedMatch(heading, cleaned, anchor)


def insert_heading(headings: list[dict], before_verse: int, text: str) -> bool:
    """Insert a heading in ascending ``before_verse`` order; skip exact duplicates.

    Returns True if inserted, False if an identical entry already existed.
    """
    for h in headings:
        if h.get("before_verse") == before_verse and h.get("text") == text:
            return False
    entry = {"before_verse": before_verse, "text": text}
    pos = 0
    for i, h in enumerate(headings):
        if h.get("before_verse", 0) <= before_verse:
            pos = i + 1
    headings.insert(pos, entry)
    return True


def clean_translation(data: dict) -> list[dict]:
    """Strip fused headings from one translation in place; return per-change records."""
    changes: list[dict] = []
    code = data.get("code", "?")
    for book in data.get("books", []):
        chapters = book.get("chapters", [])
        for ci, chapter in enumerate(chapters):
            verses = chapter.get("verses", [])
            if not verses:
                continue
            max_verse = max(v["number"] for v in verses)
            for verse in verses:
                match = fused_heading(verse.get("text", ""))
                if match is None:
                    continue
                tail = match.heading
                verse["text"] = match.cleaned

                # The section opens at the verse after the old section's last verse — the
                # stray number (an omitted verse) when present, else this verse's number.
                base = (match.anchor + 1) if match.anchor is not None else verse["number"] + 1
                if base <= max_verse:
                    target = chapter
                    before_verse = base
                elif ci + 1 < len(chapters):
                    target = chapters[ci + 1]
                    before_verse = 1
                else:
                    # Last verse of the last chapter of a book: nowhere to anchor.
                    changes.append(
                        {
                            "code": code,
                            "ref": f"{book['abbreviation']} {chapter['number']}:{verse['number']}",
                            "book": book["abbreviation"],
                            "chapter": chapter["number"],
                            "verse": verse["number"],
                            "heading": tail,
                            "before_verse": None,
                            "skipped": True,
                        }
                    )
                    continue

                target.setdefault("headings", [])
                insert_heading(target["headings"], before_verse, tail)
                changes.append(
                    {
                        "code": code,
                        "ref": f"{book['abbreviation']} {chapter['number']}:{verse['number']}",
                        "book": book["abbreviation"],
                        "chapter": chapter["number"],
                        "verse": verse["number"],
                        "heading": tail,
                        "before_verse": before_verse,
                        "skipped": False,
                    }
                )
    return changes


def write_manifest(changes: list[dict], corroboration: dict, md_path: Path, csv_path: Path) -> None:
    """Write the human-readable (.md) and machine-readable (.csv) change manifests."""
    rows = sorted(changes, key=lambda c: (c["code"], c["book"], c["chapter"], c["verse"]))

    csv_lines = ["code,ref,before_verse,heading,corroboration,low_confidence,skipped"]
    for c in rows:
        n = corroboration[(c["book"], c["chapter"], c["verse"], c["heading"])]
        heading = c["heading"].replace('"', '""')
        csv_lines.append(
            f'{c["code"]},{c["ref"]},{c["before_verse"]},"{heading}",{n},'
            f"{int(n < 2)},{int(c['skipped'])}"
        )
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    low = [
        c for c in rows if corroboration[(c["book"], c["chapter"], c["verse"], c["heading"])] < 2
    ]
    skipped = [c for c in rows if c["skipped"]]
    md = [
        "# Fused-heading cleanup manifest (issue #67)",
        "",
        f"Total strips: **{len(rows)}** across "
        f"**{len({c['code'] for c in rows})}** translations. "
        f"Low-confidence (single-translation) strips: **{len(low)}**. "
        f"Unanchored/skipped: **{len(skipped)}**.",
        "",
        "`LOW_CONFIDENCE` = the same (verse, heading) was not corroborated by any other "
        "translation; applied per the title-case rule (issue #67 decision).",
        "",
        "| Translation | Reference | before_verse | Heading | Corrob. | Flag |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for c in rows:
        n = corroboration[(c["book"], c["chapter"], c["verse"], c["heading"])]
        flag = "SKIPPED" if c["skipped"] else ("LOW_CONFIDENCE" if n < 2 else "")
        md.append(
            f"| {c['code']} | {c['ref']} | {c['before_verse']} | {c['heading']} | {n} | {flag} |"
        )
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/translations", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="detect and write the manifest, but do not modify JSON",
    )
    args = parser.parse_args(argv)

    files = sorted(args.data_dir.glob("*.json"))
    if not files:
        print(f"No translation JSON found under {args.data_dir}", file=sys.stderr)
        return 1

    # Pass A — corroboration map: how many translations share each fused (ref, heading).
    corroboration: dict[tuple, int] = defaultdict(int)
    parsed: dict[Path, dict] = {}
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        parsed[path] = data
        for book in data.get("books", []):
            for chapter in book.get("chapters", []):
                for verse in chapter.get("verses", []):
                    match = fused_heading(verse.get("text", ""))
                    if match is not None:
                        corroboration[
                            (
                                book["abbreviation"],
                                chapter["number"],
                                verse["number"],
                                match.heading,
                            )
                        ] += 1

    # Pass B — apply per file, re-dump only changed files with byte-identical formatting.
    all_changes: list[dict] = []
    per_translation: dict[str, int] = {}
    for path in files:
        data = parsed[path]
        original = path.read_text(encoding="utf-8")
        changes = clean_translation(data)
        if not changes:
            continue
        per_translation[data.get("code", path.stem)] = len(changes)
        all_changes.extend(changes)
        if not args.dry_run:
            dumped = json.dumps(data, indent=2, ensure_ascii=False)
            dumped = dumped + "\n" if original.endswith("\n") else dumped
            path.write_text(dumped, encoding="utf-8")

    md_path = Path(__file__).with_name("fused_headings_manifest.md")
    csv_path = Path(__file__).with_name("fused_headings_manifest.csv")
    write_manifest(all_changes, corroboration, md_path, csv_path)

    skipped = sum(1 for c in all_changes if c["skipped"])
    low = sum(
        1
        for c in all_changes
        if corroboration[(c["book"], c["chapter"], c["verse"], c["heading"])] < 2
    )
    mode = "DRY-RUN (no files written)" if args.dry_run else "applied"
    print(
        f"Fused-heading cleanup {mode}: {len(all_changes)} strips "
        f"across {len(per_translation)} translations."
    )
    for code in sorted(per_translation, key=lambda c: -per_translation[c]):
        print(f"  {code:7} {per_translation[code]}")
    print(f"  low-confidence (single-translation): {low}")
    print(f"  unanchored/skipped: {skipped}")
    print(f"Manifest: {md_path} , {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
