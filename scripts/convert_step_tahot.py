"""Convert the STEPBible Amalgamated Hebrew OT (TAHOT) into Concord files.

STEPBible-Data (github.com/STEPBible/STEPBible-Data) publishes ``TAHOT`` — the Hebrew OT (a
corrected Westminster Leningrad Codex, from the OpenScriptures/WLC tradition) with every word
tagged with a disambiguated Strong's number, morphology and gloss, under **CC BY 4.0**. This
script reads the four ``TAHOT`` text files and emits **two** files: ``data/translations/OSHB.json``
— the Hebrew OT loaded as an ordinary Concord translation (``language="hbo"``, ``direction="rtl"``)
— and ``data/strongs/tokens-oshb.json``, the per-word tagged tokens for word study (v6 S5).

**Versification.** TAHOT references are **English/NRSV** with the Masoretic ref trailing in
brackets, e.g. ``Mal.4.6(3.24)#10=L``. We parse the **English** primary reference (ignoring the
``(Heb)`` bracket), so OSHB's chapter/verse numbers match the English Bibles — Malachi has 4
chapters, Joel 3 — and ``?text=OSHB`` queries use the same numbers as every other endpoint. (We do
not map between schemes; cross-scheme versification mapping is a deliberate non-goal.) Psalm titles
are English **verse 0** (``Psa.3.0(3.1)``); English Bibles don't number titles, so verse-0 rows are
**skipped** (and counted).

TAHOT columns (tab-separated): ``[0]`` ``Gen.1.1#01=L`` (English ref + ``(Heb)`` bracket + word
position + ``=`` manuscript tag), ``[1]`` Hebrew (morphemes separated by ``/``, punctuation by
``\\``), ``[4]`` dStrongs (root in ``{}``), ``[5]`` Grammar, ``[8]`` Root dStrong+Instance (the
head-word Strong's, e.g. ``H7225G``). The surface form is the Hebrew with the ``/`` and ``\\``
separators removed, NFC-normalized; the token's ``strongs_id`` is the collapsed-base root Strong's
(``H0853_A`` → ``H853``, disambiguation/instance suffix dropped) and ``morph_code`` is the root
element of the grammar column. Compound Hebrew words (prefix + root + suffix) stay **whole-word**
in v1 — one token per word position, carrying the root's Strong's and morphology.

Book codes resolve through Concord's own table (``docs/canonical-books.md``) — all 39 OT codes
(``Jol``, ``Ezk``, ``Nam``, ``Sng`` …) are seeded aliases. Deterministic (canonical order) →
byte-identical re-runs. The raw TAHOT files are re-derivable and **not committed** (they live in
``data/original/``, gitignored); provenance is in ``data/SOURCES.md``.

    # default: data/original/TAHOT*.txt -> OSHB.json + tokens-oshb.json
    python scripts/convert_step_tahot.py
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
from convert_step_tagnt import load_book_table

CODE = "OSHB"
NAME = "Open Scriptures Hebrew Bible"
LANGUAGE = "hbo"  # ISO 639-3, Ancient Hebrew (no 639-1 code exists)
DIRECTION = "rtl"
COPYRIGHT = (
    "Hebrew Old Testament (Westminster Leningrad Codex tradition) derived from the STEPBible "
    "Amalgamated Hebrew OT (TAHOT). Data created by STEPBible.org based on work at Tyndale House "
    "Cambridge, CC BY 4.0, ultimately from the OpenScriptures/WLC text. "
    "Source: github.com/STEPBible/STEPBible-Data."
)

# A TAHOT data row's first column: English Book.Chapter.Verse, then an optional (Heb) bracket, then
# '#<word-position>'. The bare (English) reference is captured; the bracket is ignored.
_REF_RE = re.compile(r"^([A-Za-z0-9]+)\.(\d+)\.(\d+)")
_POS_RE = re.compile(r"#(\d+)")
# The root Strong's (col 8) collapsed to its base: letter + number, leading zeros + any
# instance/disambiguation suffix (``_A``, ``G`` …) dropped. ``H0853_A`` → ``H853``.
_ROOT_RE = re.compile(r"^([GH])0*(\d+)")

# A single tagged word: (position, surface_form, strongs_id, morph_code).
Token = tuple[int, str, str | None, str | None]


def _surface(hebrew_col: str) -> str:
    """The Hebrew surface word, NFC-normalized: the ``/`` (morpheme) and ``\\`` (punctuation)
    separators STEPBible inserts are removed, leaving the pointed/cantillated text."""
    return unicodedata.normalize("NFC", hebrew_col.replace("/", "").replace("\\", "").strip())


def _root_strongs(root_col: str) -> str | None:
    """Collapse the Root dStrong+Instance column to a base Strong's id, or ``None`` if absent."""
    m = _ROOT_RE.match(root_col.strip())
    return f"{m.group(1)}{int(m.group(2))}" if m else None


def _root_morph(dstrong_col: str, grammar_col: str) -> str | None:
    """The morphology of the head word: the grammar element aligned with the ``{root}`` dStrong.

    dStrongs/grammar are ``/``-separated per morpheme (prefix/root/suffix); the root is the element
    in ``{curly braces}``. Falls back to the whole grammar string if alignment fails."""
    d_parts = dstrong_col.split("/")
    g_parts = grammar_col.split("/")
    for i, part in enumerate(d_parts):
        if "{" in part:
            if i < len(g_parts) and g_parts[i].strip():
                return g_parts[i].strip()
            break
    return grammar_col.strip() or None


def convert(
    inputs: list[Path], alias_to_code: dict[str, str]
) -> tuple[dict[tuple[str, int, int], dict[int, Token]], dict[str, int]]:
    """Read the TAHOT files → ``{(book_id, chapter, verse): {position: Token}}`` plus skip stats."""
    verses: dict[tuple[str, int, int], dict[int, Token]] = {}
    stats = {
        "rows": 0,
        "kept": 0,
        "skipped_verse_0": 0,
        "skipped_unresolved_book": 0,
        "skipped_empty_surface": 0,
        "skipped_dup_position": 0,
    }

    for path in inputs:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            cols = line.split("\t")
            if len(cols) < 9:
                continue
            ref_m = _REF_RE.match(cols[0])
            pos_m = _POS_RE.search(cols[0])
            if ref_m is None or pos_m is None:
                continue  # header / intro / non-data row
            stats["rows"] += 1

            chapter, verse = int(ref_m.group(2)), int(ref_m.group(3))
            if verse == 0:
                stats["skipped_verse_0"] += 1  # Psalm title — no English verse number
                continue

            book_id = alias_to_code.get(normalize(ref_m.group(1)))
            if book_id is None:
                stats["skipped_unresolved_book"] += 1
                continue
            position = int(pos_m.group(1))

            surface = _surface(cols[1])
            if not surface:
                stats["skipped_empty_surface"] += 1
                continue

            slot = verses.setdefault((book_id, chapter, verse), {})
            if position in slot:
                stats["skipped_dup_position"] += 1  # a later manuscript variant for this word
                continue
            strongs_id = _root_strongs(cols[8])
            morph = _root_morph(cols[4], cols[5])
            slot[position] = (position, surface, strongs_id, morph)
            stats["kept"] += 1

    return verses, stats


def verse_text_from(
    verses: dict[tuple[str, int, int], dict[int, Token]],
) -> dict[tuple[str, int, int], str]:
    """Each verse's words joined as running text in word-position order (token[1] = surface)."""
    return {ref: " ".join(words[p][1] for p in sorted(words)) for ref, words in verses.items()}


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
        "direction": DIRECTION,
        "copyright": COPYRIGHT,
        "books": books,
    }


def build_tokens_payload(
    verses: dict[tuple[str, int, int], dict[int, Token]], code_to_meta: dict[str, tuple[int, str]]
) -> dict[str, Any]:
    """Assemble the tagged-tokens JSON: every word in canonical book/ch/verse/position order."""
    tokens: list[dict[str, Any]] = []
    for ref in sorted(verses, key=lambda r: (code_to_meta[r[0]][0], r[1], r[2])):
        book_id, chapter, verse = ref
        for position, surface, strongs_id, morph in (verses[ref][p] for p in sorted(verses[ref])):
            tokens.append(
                {
                    "book": book_id,
                    "chapter": chapter,
                    "verse": verse,
                    "position": position,
                    "surface_form": surface,
                    "strongs_id": strongs_id,
                    "morph_code": morph,
                }
            )
    return {"text_id": CODE, "source": COPYRIGHT, "tokens": tokens}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=sorted(Path("data/original").glob("TAHOT*.txt")),
        help="TAHOT text files (default: data/original/TAHOT*.txt).",
    )
    parser.add_argument("--output", type=Path, default=Path("data/translations/OSHB.json"))
    parser.add_argument("--tokens-output", type=Path, default=Path("data/strongs/tokens-oshb.json"))
    parser.add_argument("--canon", type=Path, default=Path("docs/canonical-books.md"))
    args = parser.parse_args(argv)

    if not args.input:
        raise SystemExit(
            "no TAHOT input files found. Download them from github.com/STEPBible/STEPBible-Data "
            "into data/original/ (see data/SOURCES.md), or pass --input."
        )

    alias_to_code, code_to_meta = load_book_table(args.canon)
    verses, stats = convert(list(args.input), alias_to_code)
    payload = build_payload(verse_text_from(verses), code_to_meta)
    tokens_payload = build_tokens_payload(verses, code_to_meta)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.tokens_output.parent.mkdir(parents=True, exist_ok=True)
    args.tokens_output.write_text(
        json.dumps(tokens_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    n_books = len(payload["books"])
    n_verses = sum(len(c["verses"]) for b in payload["books"] for c in b["chapters"])
    print(f"Wrote {args.output}: {n_books} books, {n_verses} verses, {stats['kept']} words.")
    print(f"Wrote {args.tokens_output}: {len(tokens_payload['tokens'])} tokens.")
    skipped = {k: v for k, v in stats.items() if k.startswith("skipped_") and v}
    if skipped:
        print(f"  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
