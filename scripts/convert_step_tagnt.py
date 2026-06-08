"""Convert the STEPBible Amalgamated Greek NT (TAGNT) into a Concord translation file.

STEPBible-Data (github.com/STEPBible/STEPBible-Data) publishes ``TAGNT`` — every word of the
standard Greek NT editions (NA28/27, SBL, TR, Byz, Tyndale House, WH, Tregelles) tagged with a
disambiguated Strong's number, morphology, lemma and gloss, under **CC BY 4.0**. This script
reads the two TAGNT text files and emits ``data/translations/SBLGNT.json`` — the Greek NT loaded
as an ordinary Concord translation (the "original-language text as a translation" idea), so
``/v1/verses/{ref}?translation=SBLGNT`` and ``/v1/translations`` work through the existing
machinery with no loader changes.

**SBL edition selection.** TAGNT is an *amalgamated* text: each word's ``editions`` column lists
which printed editions contain it (e.g. ``NA28+NA27+Tyn+SBL+WH+Treg+TR+Byz``). We keep only the
words present in the **SBL** edition, so the reconstructed text is the SBLGNT word-selection —
e.g. it drops the Textus-Receptus-only αὐτοῦ in John 3:16 and omits the TR/Byz-only John 5:4.
The surface spelling/punctuation is STEPBible's (NA-based), so this is the SBL *word selection*
rather than a byte-faithful reproduction of the printed SBLGNT; the attribution says so.

TAGNT columns (tab-separated; ``Word & Type`` first): ``Mat.1.2#01=NKO`` (reference + word
index + edition code), ``Greek`` as ``surface (translit)``, ``English``, ``dStrong=Grammar``,
``lemma=Gloss``, ``editions``, … The reference uses NRSV versification (NT chapter counts are
standard, so SBLGNT loads alongside the English translations); alternative versification numbers
trail in ``[]``/``()``/``{}`` after the bare reference and are ignored here. Verse text is the
SBL words joined in word-index order, transliteration stripped.

Book codes resolve through Concord's own table (``docs/canonical-books.md`` via
``bible_core.normalize``) — never invented here; STEPBible's codes (``Mrk``, ``Jhn``, ``Php`` …)
are all seeded aliases. Deterministic: books/chapters/verses/words in canonical order →
byte-identical re-runs. The raw TAGNT files are re-derivable and **not committed** (they live in
``data/original/``, gitignored); provenance is in ``data/SOURCES.md``.

    # default: data/original/TAGNT*.txt -> data/translations/SBLGNT.json
    python scripts/convert_step_tagnt.py
    python scripts/convert_step_tagnt.py --input path/to/TAGNT*.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from bible_core.normalize import normalize

CODE = "SBLGNT"
NAME = "SBL Greek New Testament"
LANGUAGE = "grc"  # ISO 639-3, Ancient Greek (no 639-1 code exists)
COPYRIGHT = (
    "Greek New Testament (SBL edition word-selection) derived from the STEPBible Amalgamated "
    "Greek New Testament (TAGNT). Data created by STEPBible.org based on work at Tyndale House "
    "Cambridge, CC BY 4.0; the SBLGNT is © 2010 Society of Biblical Literature and Logos "
    "Bible Software, CC BY 4.0. Source: github.com/STEPBible/STEPBible-Data."
)

# The edition whose words we keep (the value as it appears in TAGNT's '+'-joined editions column).
SBL_EDITION = "SBL"

# A TAGNT data row's first column: Book.Chapter.Verse, then optional alt-versification bracket,
# then '#<word-index>'. The bare (NRSV) reference is captured; bracketed alternatives are ignored.
_REF_RE = re.compile(r"^([A-Za-z0-9]+)\.(\d+)\.(\d+)")
_POS_RE = re.compile(r"#(\d+)")
# Trailing transliteration parenthetical on the Greek column, e.g. "κόσμον, (kosmon)".
_TRANSLIT_RE = re.compile(r"\s*\([^()]*\)\s*$")
# A canonical-books.md row: | # | CODE | Name | Testament | aliases |
_CANON_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([A-Z0-9]+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|([^|]*)\|"
)


def load_book_table(canon_path: Path) -> tuple[dict[str, str], dict[str, tuple[int, str]]]:
    """Parse docs/canonical-books.md into (alias->code, code->(canonical_order, name)).

    Source of truth for book identity (CLAUDE.md) — never invent reference data. Both the code
    and every listed alias resolve to the USFM code; the order/name feed the translation file's
    required ``order_index``/``name`` (which the loader cross-checks against the seed).
    """
    alias_to_code: dict[str, str] = {}
    code_to_meta: dict[str, tuple[int, str]] = {}
    for line in canon_path.read_text("utf-8").splitlines():
        m = _CANON_ROW.match(line)
        if m is None:
            continue
        order, code, name, _testament, aliases = (
            int(m.group(1)),
            m.group(2),
            m.group(3),
            m.group(4),
            m.group(5),
        )
        code_to_meta[code] = (order, name)
        alias_to_code[normalize(code)] = code
        for alias in aliases.split(","):
            alias = alias.strip()
            if alias:
                alias_to_code[normalize(alias)] = code
    if len(code_to_meta) != 66:
        raise SystemExit(f"expected 66 book codes from {canon_path}, found {len(code_to_meta)}.")
    return alias_to_code, code_to_meta


def _surface(greek_col: str) -> str:
    """The Greek surface word: trailing ``(translit)`` removed, normalized to NFC.

    STEPBible's text is not canonically composed; NFC is the conventional form for a Greek
    text API (consistent display, search, and stable ETags downstream)."""
    return unicodedata.normalize("NFC", _TRANSLIT_RE.sub("", greek_col).strip())


def convert(
    inputs: list[Path], alias_to_code: dict[str, str]
) -> tuple[dict[tuple[str, int, int], str], dict[str, int]]:
    """Read the TAGNT files → ``{(book_id, chapter, verse): text}`` plus skip stats.

    Verse text is the SBL words joined in word-index order; tokens are deduped by position
    (first wins) defensively.
    """
    # (book_id, chapter, verse) -> {position: surface}
    verses: dict[tuple[str, int, int], dict[int, str]] = {}
    stats = {
        "rows": 0,
        "kept": 0,
        "skipped_not_sbl": 0,
        "skipped_unresolved_book": 0,
        "skipped_empty_surface": 0,
        "skipped_dup_position": 0,
    }

    for path in inputs:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            cols = line.split("\t")
            if len(cols) < 6:
                continue
            ref_m = _REF_RE.match(cols[0])
            pos_m = _POS_RE.search(cols[0])
            if ref_m is None or pos_m is None:
                continue  # header / intro / non-data row
            stats["rows"] += 1

            editions = {e.strip() for e in cols[5].split("+")}
            if SBL_EDITION not in editions:
                stats["skipped_not_sbl"] += 1
                continue

            book_id = alias_to_code.get(normalize(ref_m.group(1)))
            if book_id is None:
                stats["skipped_unresolved_book"] += 1
                continue
            chapter, verse, position = int(ref_m.group(2)), int(ref_m.group(3)), int(pos_m.group(1))

            surface = _surface(cols[1])
            if not surface:
                stats["skipped_empty_surface"] += 1
                continue

            slot = verses.setdefault((book_id, chapter, verse), {})
            if position in slot:
                stats["skipped_dup_position"] += 1
                continue
            slot[position] = surface
            stats["kept"] += 1

    # Collapse each verse's positioned words into running text (word-index order).
    verse_text: dict[tuple[str, int, int], str] = {
        ref: " ".join(words[p] for p in sorted(words)) for ref, words in verses.items()
    }
    return verse_text, stats


def build_payload(
    verse_text: dict[tuple[str, int, int], str], code_to_meta: dict[str, tuple[int, str]]
) -> dict[str, Any]:
    """Assemble the Concord translation JSON (books/chapters/verses in canonical order)."""
    by_book: dict[str, dict[int, dict[int, str]]] = {}
    for (book_id, chapter, verse), txt in verse_text.items():
        by_book.setdefault(book_id, {}).setdefault(chapter, {})[verse] = txt

    books: list[dict[str, Any]] = []
    for book_id in sorted(by_book, key=lambda b: code_to_meta[b][0]):
        order_index, name = code_to_meta[book_id]
        chapters = [
            {
                "number": chapter,
                "verses": [
                    {"number": v, "text": by_book[book_id][chapter][v]}
                    for v in sorted(by_book[book_id][chapter])
                ],
            }
            for chapter in sorted(by_book[book_id])
        ]
        books.append(
            {
                "name": name,
                "abbreviation": book_id,
                "order_index": order_index,
                "chapters": chapters,
            }
        )

    return {
        "code": CODE,
        "name": NAME,
        "language": LANGUAGE,
        "copyright": COPYRIGHT,
        "books": books,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=sorted(Path("data/original").glob("TAGNT*.txt")),
        help="TAGNT text files (default: data/original/TAGNT*.txt).",
    )
    parser.add_argument("--output", type=Path, default=Path("data/translations/SBLGNT.json"))
    parser.add_argument("--canon", type=Path, default=Path("docs/canonical-books.md"))
    args = parser.parse_args(argv)

    if not args.input:
        raise SystemExit(
            "no TAGNT input files found. Download them from github.com/STEPBible/STEPBible-Data "
            "into data/original/ (see data/SOURCES.md), or pass --input."
        )

    alias_to_code, code_to_meta = load_book_table(args.canon)
    verse_text, stats = convert(list(args.input), alias_to_code)
    payload = build_payload(verse_text, code_to_meta)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(text, encoding="utf-8")

    n_books = len(payload["books"])
    n_verses = sum(len(c["verses"]) for b in payload["books"] for c in b["chapters"])
    print(f"Wrote {args.output}: {n_books} books, {n_verses} verses, {stats['kept']} SBL words.")
    skipped = {k: v for k, v in stats.items() if k.startswith("skipped_") and v}
    if skipped:
        print(f"  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
