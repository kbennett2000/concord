"""Convert the STEPBible Greek lexicon (TBESG) into a Concord Strong's lexicon file.

STEPBible-Data (github.com/STEPBible/STEPBible-Data) publishes ``TBESG`` — the *Translators Brief
lexicon of Extended Strongs for Greek* — under **CC BY 4.0**. It carries, for every Extended
Strong's number, the Greek lemma, transliteration, morphology, a one-word gloss, and a full
Abbott-Smith definition. This script reads that text file and emits ``data/strongs/lexicon.json``
— the lexicon loaded into Concord's additive ``strongs_entries`` table, so ``/v1/strongs`` and
``/v1/strongs/{id}`` work through ``bible-core`` with pure SQLite (no embeddings).

**Format.** TBESG is tab-separated. A long header/licence block and a ``$======``-delimited
"PERSON(s)" section precede the data; the real lexicon rows begin with a bare Extended Strong's
number in the first column (``G0001``, ``G0026`` …). Columns, in order:

    eStrong | dStrong | uStrong | Greek (lemma) | Transliteration | Morph | Gloss | Meaning (HTML)

We take the lemma, transliteration, gloss, and (HTML-stripped) meaning; the morphology is a
word-level attribute that belongs on tokens (a later slice), not on the lexicon entry.

**Strong's id (flat v1).** The id is the eStrong column collapsed to its base — the letter plus the
number with leading zeros dropped: ``G0026`` → ``G26``. The same base can appear on several rows
(``G0001G`` "Alpha" and ``G0001H`` the interjection ``ἆ`` both carry eStrong ``G0001``); the **first
row wins** (the primary sense). Disambiguated senses are deferred (the "flat topics" precedent).

The raw TBESG file is re-derivable and **not committed** (it lives in ``data/original/``,
gitignored); provenance is in ``data/SOURCES.md``. Deterministic: entries are sorted by Strong's id
so re-runs are byte-identical.

    # default: data/original/TBESG*.txt -> data/strongs/lexicon.json
    python scripts/convert_strongs_lexicon.py
    python scripts/convert_strongs_lexicon.py --input path/to/TBESG.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

SOURCE = "STEP Bible (Tyndale House)"
LANGUAGE = "grc"  # ISO 639-3, Ancient Greek (no 639-1 code exists)

# A lexicon data row's first column is a bare Extended Strong's number: letter + digits and nothing
# else. Header text, the "Fields:" doc, ``$======`` section markers and the "PERSON(s)" rows (whose
# first column is a name like ``Herod@Mat.2.1=G2264G`` or ``- Named``) all fail this → skipped.
_ESTRONG_RE = re.compile(r"^([GH])(\d+)$")
# HTML in the Meaning column: line breaks become spaces, every other tag (``<b>``, ``<i>``,
# ``<ref='…'>…</ref>``, ``<re>…</re>`` …) is removed keeping its visible inner text.
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def collapse_strongs(estrong: str) -> str | None:
    """``G0026`` -> ``G26`` (letter + zero-stripped number); ``None`` if not a Strong's number."""
    m = _ESTRONG_RE.match(estrong)
    if m is None:
        return None
    return f"{m.group(1)}{int(m.group(2))}"


def strip_html(meaning: str) -> str:
    """Plain text from the HTML Meaning column: drop tags, keep inner text, collapse whitespace.

    ``<BR />`` becomes a space (so adjacent points don't glue); the ``__`` indent markers STEPBible
    uses for sub-points are dropped. The ``†`` dagger and ``(AS)`` attribution are kept verbatim."""
    text = _BR_RE.sub(" ", meaning)
    text = _TAG_RE.sub("", text)
    text = text.replace("__", "")
    return _WS_RE.sub(" ", text).strip()


def convert(inputs: list[Path]) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Read the TBESG file(s) -> a list of lexicon entries + skip stats (first sense per base)."""
    by_id: dict[str, dict[str, str]] = {}
    stats = {
        "rows": 0,
        "kept": 0,
        "skipped_short": 0,
        "skipped_dup_base": 0,
        "skipped_empty": 0,
    }

    for path in inputs:
        for line in path.read_text(encoding="utf-8").splitlines():
            cols = line.split("\t")
            strongs_id = collapse_strongs(cols[0].strip()) if cols else None
            if strongs_id is None:
                continue  # header / fields doc / $ section / PERSON row — not a lexicon entry
            stats["rows"] += 1

            if len(cols) < 8:
                stats["skipped_short"] += 1
                continue
            if strongs_id in by_id:
                stats["skipped_dup_base"] += 1
                continue

            lemma = unicodedata.normalize("NFC", cols[3].strip())
            transliteration = unicodedata.normalize("NFC", cols[4].strip())
            gloss = cols[6].strip()
            definition = strip_html(cols[7])
            if not lemma or not gloss:
                stats["skipped_empty"] += 1
                continue

            by_id[strongs_id] = {
                "strongs_id": strongs_id,
                "language": LANGUAGE,
                "lemma": lemma,
                "transliteration": transliteration,
                "gloss": gloss,
                "definition": definition,
            }
            stats["kept"] += 1

    entries = [by_id[k] for k in sorted(by_id, key=lambda s: (s[0], int(s[1:])))]
    return entries, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=sorted(Path("data/original").glob("TBESG*.txt")),
        help="TBESG text file(s) (default: data/original/TBESG*.txt).",
    )
    parser.add_argument("--output", type=Path, default=Path("data/strongs/lexicon.json"))
    args = parser.parse_args(argv)

    if not args.input:
        raise SystemExit(
            "no TBESG input files found. Download the lexicon from "
            "github.com/STEPBible/STEPBible-Data into data/original/ "
            "(see data/SOURCES.md), or pass --input."
        )

    entries, stats = convert(list(args.input))
    payload: dict[str, Any] = {"source": SOURCE, "entries": entries}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(text, encoding="utf-8")

    print(f"Wrote {args.output}: {len(entries)} Strong's entries.")
    skipped = {k: v for k, v in stats.items() if k.startswith("skipped_") and v}
    if skipped:
        print(f"  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
