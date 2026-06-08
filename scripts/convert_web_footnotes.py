"""Extract the World English Bible's public-domain footnotes from USFM into Concord notes JSON.

The WEB is public domain ("not copyrighted"), and so are its translator footnotes. eBible.org's
USFM distribution (``engwebp`` — World English Bible Protestant Edition) carries them inline as
``\\f … \\f*`` notes, e.g.::

    \\v 1 … God\\f + \\fr 1:1 \\ft The Hebrew word rendered "God" is "…" (Elohim).\\f* created …

This script reads a directory of those USFM book files and emits **footnotes only** (never the
verse text — Concord already ships WEB's text; re-deriving it risks drift) as the v4 notes
contract (``docs/v4/notes-ingest.md``), written to ``data/notes/WEB.json`` — the committed,
ship-by-default public notes path (ADR-0004).

Field mapping (verse-level anchor for v1):
- ``book``    — the USFM ``\\id`` code (GEN, 1CO, …), which Concord resolves via its seeded aliases.
- ``chapter``/``verse`` — from the footnote's ``\\fr`` origin reference when present, else the
  enclosing ``\\c``/``\\v``.
- ``text``    — the footnote body with USFM markers stripped to clean prose.
- ``type``    — **null** (omitted). WEB footnotes mix textual-variant / alternate-rendering /
  measurement notes; no single category is honest, and the contract permits null.
- ``char_offset`` — **0** (verse-level). A precise in-verse offset would require aligning the USFM
  text to Concord's stored WEB text (different derivation/punctuation) — fragile; deferred.
- ``marker``  — the source caller, or null for the auto-callers ``+``/``-`` (not a displayed mark).
- ``cross_references`` — **[]**. Parsing referenced verses out of footnote prose is unreliable;
  skipped for v1 (the contract makes them optional).

Only the 66 canonical books are emitted; front-matter / glossary files are skipped (their ``\\id``
codes are not in the canon set, sourced from ``docs/canonical-books.md`` — never invented here).
Malformed footnotes are skipped and counted so the emitted file is guaranteed loadable.

The raw USFM is re-derivable and not committed; the derived ``data/notes/WEB.json`` is (it is PD
and ships anyway). Provenance: see ``data/SOURCES.md`` and ``THIRD_PARTY_NOTICES``.

    # default: data/web-usfm/*.usfm -> data/notes/WEB.json
    python scripts/convert_web_footnotes.py --usfm-dir /path/to/engwebp_usfm
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# A USFM marker is a backslash, an optional nesting "+", letters/digits, and (for an end
# marker) a trailing "*".  We strip them to recover the footnote's plain prose.
_ID_RE = re.compile(r"\\id\s+(\S+)")
_FR_RE = re.compile(r"\\fr\s+(\d+)[:.](\d+)")
_FR_STRIP_RE = re.compile(r"\\fr\s+\S+\s?")
_ATTR_RE = re.compile(r'\|[a-z0-9]+="[^"]*"', re.IGNORECASE)
_END_MARKER_RE = re.compile(r"\\\+?[a-z0-9]+\*")
_OPEN_MARKER_RE = re.compile(r"\\\+?[a-z0-9]+\s?")
_WS_RE = re.compile(r"\s+")

# Chapter, verse, or a whole footnote — scanned in document order so each footnote inherits the
# enclosing \c/\v.  `\f\s` (a space after f) distinguishes a footnote-open from \fr/\ft/\fq.
_TOKEN_RE = re.compile(
    r"\\c\s+(\d+)"  # 1: chapter
    r"|\\v\s+(\d+)"  # 2: verse (leading int of a range)
    r"|\\f\s+(\S+)\s+(.*?)\\f\*",  # 3: caller, 4: body
    re.DOTALL,
)


def load_canon_codes(canon_path: Path) -> set[str]:
    """The 66 canonical USFM codes, read from the repo's source-of-truth book table.

    Parses rows of ``| <n> | <CODE> | …`` from ``docs/canonical-books.md`` so we never invent
    reference data here (CLAUDE.md). Anything not in this set (front matter, glossary) is skipped.
    """
    row = re.compile(r"^\|\s*\d+\s*\|\s*([A-Z0-9]+)\s*\|")
    codes = {
        m.group(1)
        for line in canon_path.read_text("utf-8").splitlines()
        if (m := row.match(line)) is not None
    }
    if len(codes) != 66:
        raise SystemExit(
            f"expected 66 canonical book codes in {canon_path}, found {len(codes)} — "
            "the table format may have changed."
        )
    return codes


def clean_text(body: str) -> str:
    """Strip USFM markers / attributes from a footnote body, leaving clean prose."""
    body = _FR_STRIP_RE.sub(" ", body)  # drop the \fr origin ref (used only for anchoring)
    body = _ATTR_RE.sub("", body)  # drop |strong="…" style attributes
    body = _END_MARKER_RE.sub("", body)  # drop end markers: \wh*, \+wh*, \ft*
    body = _OPEN_MARKER_RE.sub("", body)  # drop open markers: \ft, \fq, \+wh, …
    return _WS_RE.sub(" ", body).strip()


def extract_book(text: str, canon: set[str], stats: dict[str, int]) -> list[dict[str, Any]]:
    """Extract footnotes from one USFM book, anchored by \\fr (or the enclosing \\c/\\v)."""
    id_match = _ID_RE.search(text)
    if id_match is None:
        stats["skipped_no_id"] += 1
        return []
    book = id_match.group(1)
    if book not in canon:  # front matter, glossary, etc.
        stats["skipped_non_canon_books"] += 1
        return []

    notes: list[dict[str, Any]] = []
    chapter: int | None = None
    verse: int | None = None
    for m in _TOKEN_RE.finditer(text):
        if m.group(1) is not None:  # \c
            chapter, verse = int(m.group(1)), None
            continue
        if m.group(2) is not None:  # \v
            verse = int(m.group(2))
            continue

        caller, body = m.group(3), m.group(4)  # footnote
        fr = _FR_RE.search(body)
        anchor_ch = int(fr.group(1)) if fr else chapter
        anchor_v = int(fr.group(2)) if fr else verse
        note_text = clean_text(body)
        if anchor_ch is None or anchor_v is None or anchor_ch < 1 or anchor_v < 1:
            stats["skipped_no_anchor"] += 1
            continue
        if not note_text:
            stats["skipped_empty_text"] += 1
            continue

        notes.append(
            {
                "book": book,
                "chapter": anchor_ch,
                "verse": anchor_v,
                "text": note_text,
                "type": None,
                "char_offset": 0,
                "marker": None if caller in {"+", "-"} else caller,
                "cross_references": [],
            }
        )
        stats["notes"] += 1
    return notes


def convert(
    usfm_dir: Path, canon: set[str], translation: str
) -> tuple[dict[str, Any], dict[str, int]]:
    """Return (Concord notes payload, stats). Files in sorted order, footnotes in document order
    → a deterministic, idempotent emit."""
    stats: dict[str, int] = {
        "notes": 0,
        "skipped_non_canon_books": 0,
        "skipped_no_id": 0,
        "skipped_no_anchor": 0,
        "skipped_empty_text": 0,
    }
    notes: list[dict[str, Any]] = []
    for path in sorted(usfm_dir.glob("*.usfm"), key=lambda p: p.name):
        notes.extend(extract_book(path.read_text("utf-8"), canon, stats))
    return {"translation": translation, "notes": notes}, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usfm-dir", default="data/web-usfm", type=Path)
    parser.add_argument("--output", default="data/notes/WEB.json", type=Path)
    parser.add_argument("--translation", default="WEB")
    parser.add_argument("--canon", default="docs/canonical-books.md", type=Path)
    args = parser.parse_args(argv)

    canon = load_canon_codes(args.canon)
    payload, stats = convert(args.usfm_dir, canon, args.translation)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {args.output}: translation={payload['translation']!r}, {stats['notes']} notes.")
    skipped = {k: v for k, v in stats.items() if k.startswith("skipped_") and v}
    if skipped:
        print(f"  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
