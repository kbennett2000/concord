"""Convert Nave's Topical Bible (CSV) into Concord's committed topics JSON.

Nave's Topical Bible (Orville J. Nave, 1897) is public domain; this script reads the
machine-readable compilation from BradyStephenson/bible-data (`NavesTopicalDictionary.csv`,
CC BY 4.0) and emits `data/topics/naves.json` — the committed, ship-by-default topical dataset
the loader bakes into `bible.db` (the geography/places pattern, but for topics).

CSV shape: columns `section,subject,entry`. `subject` is the topic heading; `entry` is prose
with embedded references using USFM-style book codes, e.g.::

    -WORLDLY PSA 39:6; 127:2; ECC 4:8; MAT 6:25-34; 13:22; 1CO 7:32,33; PHP 4:6

This script extracts **verse-level** references only:
- A reference group is an optional book code followed by `chapter:verse` with same-chapter
  ranges (`6:16-20`) and verse lists (`21:4,10`). A group without a book code inherits the
  current book (so `PSA 39:6; 127:2` → both Psalms).
- **Chapter-only** refs (`GEN 1; 2`, no colon) are skipped + counted: verse-level precision
  keeps the reverse (verse→topics) index honest, and whole-chapter expansion would bloat it.
- Cross-chapter ranges and unresolvable/prose tokens are skipped + counted.

A "See X" entry with no verses of its own becomes a redirect: `see_also` = the target topic's
slug, `verses: []` (faithful & flat — Nave's `entry` sub-headings are flattened into one verse
union per topic; hierarchical sub-topics are deferred).

Book codes resolve through Concord's own alias table (parsed from `docs/canonical-books.md`,
via `bible_core.normalize`) plus a small override map for Nave's non-standard codes — never
invented here. Deterministic: topics in CSV order, verses sorted + deduped → byte-identical
re-runs. The raw CSV is re-derivable and not committed; provenance is in `data/SOURCES.md`.

    # default: data/topics/NavesTopicalDictionary.csv -> data/topics/naves.json
    python scripts/convert_naves_topics.py --input <path-to-csv>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from bible_core.normalize import normalize

SOURCE_NAME = "Nave's Topical Bible"

# Nave's codes that don't normalize to a seeded alias. Mapped to the USFM code. Only verified
# equivalences (never guesses): this edition writes the Johannine epistles as `1JHN`/`2JHN`/
# `3JHN` (canonical USFM is `1JN`/`2JN`/`3JN`). The rest of its codes are standard USFM.
_OVERRIDES: dict[str, str] = {
    "1JHN": "1JN",
    "2JHN": "2JN",
    "3JHN": "3JN",
}

# A reference group: an optional book code (e.g. PHP, 1CO, Jude) then chapter:verse[list/range].
_REF_RE = re.compile(r"(?:([1-3]?[A-Za-z]{2,5})\s+)?(\d+):(\d+(?:[-,]\d+)*)")
# A "See X" redirect entry (no verses of its own): capture the target up to ; or newline.
_SEE_RE = re.compile(r"^-?\s*See\s+([^;\n]+)", re.IGNORECASE)


def load_alias_map(canon_path: Path) -> dict[str, str]:
    """normalized alias -> USFM code, from the repo's source-of-truth book table.

    Parses `| # | CODE | Name | Testament | a, b, c |` rows of docs/canonical-books.md so we
    never invent reference data here (CLAUDE.md). Both the code and every listed alias resolve.
    """
    row = re.compile(r"^\|\s*\d+\s*\|\s*([A-Z0-9]+)\s*\|[^|]*\|[^|]*\|([^|]*)\|")
    alias_map: dict[str, str] = {}
    for line in canon_path.read_text("utf-8").splitlines():
        m = row.match(line)
        if m is None:
            continue
        code = m.group(1)
        alias_map[normalize(code)] = code
        for alias in m.group(2).split(","):
            alias = alias.strip()
            if alias:
                alias_map[normalize(alias)] = code
    if len(set(alias_map.values())) != 66:
        raise SystemExit(
            f"expected 66 book codes from {canon_path}, found {len(set(alias_map.values()))}."
        )
    return alias_map


def slugify(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def _resolve(token: str, alias_map: dict[str, str]) -> str | None:
    return alias_map.get(normalize(token)) or _OVERRIDES.get(token.upper())


def _expand_versespec(spec: str) -> list[int] | None:
    """`3,8-10,14-16` -> [3,8,9,10,14,15,16]; None if any item is a malformed/backwards range."""
    verses: list[int] = []
    for item in spec.split(","):
        if "-" in item:
            lo_s, hi_s = item.split("-", 1)
            if not (lo_s.isdigit() and hi_s.isdigit()):
                return None
            lo, hi = int(lo_s), int(hi_s)
            if hi < lo or hi - lo > 200:  # backwards, or an implausible cross-chapter artifact
                return None
            verses.extend(range(lo, hi + 1))
        else:
            if not item.isdigit():
                return None
            verses.append(int(item))
    return verses


def parse_entry(
    entry: str, alias_map: dict[str, str], stats: dict[str, int]
) -> list[tuple[str, int, int]]:
    """Extract (book_code, chapter, verse) triples from one Nave's entry, in document order."""
    out: list[tuple[str, int, int]] = []
    current: str | None = None
    for m in _REF_RE.finditer(entry):
        book_token, chapter_s, versespec = m.group(1), m.group(2), m.group(3)
        if book_token is not None:
            resolved = _resolve(book_token, alias_map)
            if resolved is None:
                stats["skipped_unresolved_book"] += 1
                current = None  # don't let a later book-less ref inherit across the gap
                continue
            current = resolved
        if current is None:
            stats["skipped_no_book"] += 1
            continue
        chapter = int(chapter_s)
        verses = _expand_versespec(versespec)
        if verses is None:
            stats["skipped_bad_range"] += 1
            continue
        for v in verses:
            out.append((current, chapter, v))
    return out


def convert(csv_path: Path, alias_map: dict[str, str]) -> tuple[dict[str, Any], dict[str, int]]:
    stats = {
        "topics": 0,
        "redirects": 0,
        "verse_links": 0,
        "skipped_unresolved_book": 0,
        "skipped_no_book": 0,
        "skipped_bad_range": 0,
    }
    topics: list[dict[str, Any]] = []
    slugs: dict[str, int] = {}

    with csv_path.open(encoding="utf-8-sig") as handle:  # strip the source's UTF-8 BOM
        for record in csv.DictReader(handle):
            subject = (record.get("subject") or "").strip()
            if not subject:
                continue
            section = (record.get("section") or "").strip()
            entry = record.get("entry") or ""

            slug = slugify(subject)
            if not slug:
                continue
            if slug in slugs:  # deterministic disambiguation by CSV order
                slugs[slug] += 1
                slug = f"{slug}-{slugs[slug]}"
            else:
                slugs[slug] = 1

            triples = parse_entry(entry, alias_map, stats)
            # Dedup + canonical-ish sort (by code then chapter/verse) for a stable emit.
            verses = sorted({t for t in triples}, key=lambda t: (t[0], t[1], t[2]))

            see_also: str | None = None
            if not verses:
                see = _SEE_RE.match(entry.strip())
                if see is not None:
                    see_also = slugify(see.group(1))
                    stats["redirects"] += 1

            topics.append(
                {
                    "id": slug,
                    "name": subject,
                    "section": section,
                    "see_also": see_also,
                    "verses": [{"book": b, "chapter": c, "verse": v} for b, c, v in verses],
                }
            )
            stats["topics"] += 1
            stats["verse_links"] += len(verses)

    return {"source": SOURCE_NAME, "topics": topics}, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/topics/NavesTopicalDictionary.csv", type=Path)
    parser.add_argument("--output", default="data/topics/naves.json", type=Path)
    parser.add_argument("--canon", default="docs/canonical-books.md", type=Path)
    args = parser.parse_args(argv)

    alias_map = load_alias_map(args.canon)
    payload, stats = convert(args.input, alias_map)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print(
        f"Wrote {args.output}: {stats['topics']} topics "
        f"({stats['redirects']} redirects), {stats['verse_links']} verse links."
    )
    skipped = {k: v for k, v in stats.items() if k.startswith("skipped_") and v}
    if skipped:
        print(f"  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
