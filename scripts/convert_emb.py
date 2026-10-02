#!/usr/bin/env python3
"""Convert an operator-owned Every Man's Bible PDF into Concord's private EMB translation.

Concord v8 (docs/v8/SPEC.md). Reads the PDF with ``pdftohtml -xml`` (poppler-utils) and
writes ``data/private/EMB.json`` — verses and section headings — ``data/private/notes/EMB.json``
— its notes, features and charts — ``data/private/documents/EMB.json`` — its book
introductions, front matter, reading plan and Personal Gold authors — and its images under
``data/private/assets/EMB/``, plus working files under ``data/private/work/EMB/``. Everything
it writes stays under ``data/private/`` (git- and docker-ignored). Given the EPUB edition, it
also cross-checks the text, the notes and the documents against it; given nothing else, it
uses ``data/private/nlt.json`` (if present) only as verse cross-check evidence.

    uv run python scripts/convert_emb.py --pdf "<your EMB.pdf>" [--epub "<your EMB.epub>"]

Then ``make build-db``. Only load data you have the legal right to use
(docs/v8/emb-ingest.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from emb_convert.convert import ConvertError, convert
from emb_convert.layout import LayoutError
from emb_convert.pdfxml import PdfXmlError

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="convert_emb.py",
        description="Every Man's Bible PDF → data/private/EMB.json + notes (Concord v8).",
    )
    parser.add_argument("--pdf", required=True, type=Path, help="your Every Man's Bible PDF")
    parser.add_argument(
        "--epub", type=Path, default=None, help="the EPUB edition, to cross-check every verse"
    )
    parser.add_argument(
        "--nlt",
        type=Path,
        default=REPO_ROOT / "data" / "private" / "nlt.json",
        help="a private NLT translation file, used only as cross-check evidence",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "private",
        help="where EMB.json and work/EMB/ go (default: data/private)",
    )
    args = parser.parse_args(argv)
    if not args.pdf.is_file():
        print(f"error: no PDF at {args.pdf}", file=sys.stderr)
        return 2
    if args.epub is not None and not args.epub.is_file():
        print(f"error: no EPUB at {args.epub}", file=sys.stderr)
        return 2
    try:
        ok, text = convert(args.pdf, args.epub, args.nlt, args.out_dir)
    except (ConvertError, LayoutError, PdfXmlError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(text, end="")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
