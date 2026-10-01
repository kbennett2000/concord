"""The EMB converter's outputs: rights lines, the translation file, determinism, the CLI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bible_core.loader import build_database
from convert_emb import main
from emb_convert.convert import copyright_lines, marker_payload, translation_payload
from emb_convert.layout import find_layout
from emb_convert.pdfxml import parse_pdf_xml
from pdfxmlkit import T, body, document, header, heading, marker, parse, start, vnum

GEN = start("GEN") + 1
PAGES = {
    GEN: [
        *header("GEN", 1),
        heading("A Made-up Heading", 90),
        vnum("1", 110),
        body("Made-up words.", 110, 45, width=70),
        marker(110, 116),
        vnum("2-3", 130),
        body("Two combined.", 130, 50),
    ]
}


def test_copyright_lines_keep_only_the_rights_paragraphs() -> None:
    front = [
        T("Some Notes copyright © 2001 by A. Writer.", 79),
        T("All rights reserved.", 90),
        T("Cover photograph copyright © by Someone. All rights reserved.", 151),
        T("Holy Book, copyright © 1999 by A Foundation.", 263),
        T("All rights reserved.", 274),
        T("Quotations are from the Holy Book, copyright © 1999. Used by permission.", 403),
        T("All rights reserved.", 414),
    ]
    doc = parse_pdf_xml(document({4: front}))
    assert copyright_lines(doc, find_layout(doc)) == (
        "Some Notes copyright © 2001 by A. Writer. All rights reserved. "
        "Holy Book, copyright © 1999 by A Foundation. All rights reserved."
    )


def test_translation_file_loads_through_concords_loader(tmp_path: Path) -> None:
    result = parse(PAGES)
    data = tmp_path / "data"
    data.mkdir()
    payload = translation_payload(result, "Rights line.")
    (data / "EMB.json").write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
    stats = build_database(tmp_path / "bible.db", [data])
    assert stats.translations == 1
    with sqlite3.connect(tmp_path / "bible.db") as conn:
        rows = conn.execute("SELECT chapter, verse, text FROM verses ORDER BY verse").fetchall()
        headings = conn.execute("SELECT before_verse, text FROM section_headings").fetchall()
    assert rows == [(1, 1, "Made-up words."), (1, 2, "Two combined.")]  # 3 is absent
    assert headings == [(1, "A Made-up Heading")]


def test_markers_record_book_verse_offset_and_target() -> None:
    assert marker_payload(parse(PAGES).markers) == [
        {
            "book": "GEN",
            "chapter": 1,
            "verse": 1,
            "offset": 14,
            "in": "verse",
            "target_page": parse(PAGES).markers[0].target_page,
            "ordinal": 1,
        }
    ]


def test_same_input_gives_identical_output() -> None:
    first = json.dumps(translation_payload(parse(PAGES), "r"), ensure_ascii=False, indent=2)
    second = json.dumps(translation_payload(parse(PAGES), "r"), ensure_ascii=False, indent=2)
    assert first == second


def test_cli_refuses_missing_inputs(tmp_path: Path) -> None:
    assert main(["--pdf", str(tmp_path / "missing.pdf")]) == 2
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert main(["--pdf", str(pdf), "--epub", str(tmp_path / "missing.epub")]) == 2
