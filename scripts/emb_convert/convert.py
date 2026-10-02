"""One run: PDF → parse → checks → (cross-check) → files under ``data/private/``.

Writes, only when every structural check passes:

- ``<out>/EMB.json`` — the translation (Concord's translation contract, code ``EMB``);
- ``<out>/notes/EMB.json`` — its textual and study notes and feature articles (ADR-0011);
- ``<out>/work/EMB/markers.json`` — where each removed ``*`` sat (the textual notes' anchors);
- ``<out>/work/EMB/crosscheck.tsv`` — every verse cross-check finding by reference;
- ``<out>/work/EMB/notes-crosscheck.tsv`` — every note cross-check finding by note;
- ``<out>/work/EMB/articles-crosscheck.tsv`` — every article cross-check finding (V8-S3a);
- ``<out>/work/EMB/topics-crosscheck.tsv`` — every topic and box cross-check finding (V8-S3b);
- ``<out>/work/EMB/summary.txt`` — the printed summary.

``work/`` is never scanned by a loader. The same PDF gives byte-identical files.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from emb_convert.clean import Fixes, PublicWords, collapse
from emb_convert.crosscheck import CrossCheck, cross_check
from emb_convert.epub import parse_epub
from emb_convert.layout import Layout, canonical_books, find_layout
from emb_convert.lines import group_lines
from emb_convert.notes import (
    build_notes,
    cross_check_epub_articles,
    cross_check_epub_features,
    cross_check_epub_notes,
    notes_payload,
)
from emb_convert.pdfxml import PdfDocument, parse_pdf_xml, run_pdftohtml
from emb_convert.report import articles_summary, features_summary, notes_summary, summary
from emb_convert.skeleton import load_public_texts, load_skeleton, load_verses
from emb_convert.text import Marker, ParseResult, parse_bible
from emb_convert.validate import validate

CODE = "EMB"
NAME = "Every Man's Bible (NLT)"
LANGUAGE = "en"
PARAGRAPH_GAP = 13  # points between two lines of one paragraph on the copyright page

_RESERVED = re.compile(r"copyright ©", re.IGNORECASE)


class ConvertError(Exception):
    """The run could not produce trustworthy output."""


def copyright_lines(doc: PdfDocument, layout: Layout) -> str:
    """The book's own rights lines, read from its copyright page at run time.

    Paragraphs of the first front-matter page that holds a "copyright ©", keeping those that
    end "All rights reserved." — not the photo credits, not the quotation credit-line
    templates ("Used by permission").
    """
    front = [i for i in doc.items if i.page < layout.bible_start]
    page = next((i.page for i in front if _RESERVED.search(i.text)), None)
    if page is None:
        raise ConvertError("no copyright page found before the Bible text")
    paragraphs: list[list[str]] = []
    last_top = -100
    for line in group_lines([i for i in front if i.page == page]):
        if line.top - last_top > PARAGRAPH_GAP or not paragraphs:
            paragraphs.append([])
        paragraphs[-1].append(line.text)
        last_top = line.top
    kept = [
        text
        for text in (collapse(" ".join(p)).strip() for p in paragraphs)
        if _RESERVED.search(text)
        and text.endswith("All rights reserved.")
        and "hotograph" not in text
        and "Used by permission" not in text
    ]
    if not kept:
        raise ConvertError(f"no rights lines found on the copyright page (p{page})")
    return " ".join(kept)


def translation_payload(result: ParseResult, copyright_text: str) -> dict[str, Any]:
    return {
        "code": CODE,
        "name": NAME,
        "language": LANGUAGE,
        "copyright": copyright_text,
        "books": [
            {
                "name": book.name,
                "abbreviation": book.code,
                "order_index": book.order,
                "chapters": [
                    {
                        "number": chapter.number,
                        "verses": [
                            {"number": v.number, "text": v.text, "is_red_letter": False}
                            for v in chapter.verses
                        ],
                        "headings": [
                            {"before_verse": h.before_verse, "text": h.text}
                            for h in chapter.headings
                        ],
                    }
                    for chapter in book.chapters
                ],
            }
            for book in result.books
        ],
    }


def marker_payload(markers: list[Marker]) -> list[dict[str, Any]]:
    return [
        {
            "book": m.book,
            "chapter": m.chapter,
            "verse": m.verse,
            "offset": m.offset,
            "in": m.where.value,
            "target_page": m.target_page,
            "ordinal": m.ordinal,
        }
        for m in markers
    ]


def _texts(result: ParseResult) -> dict[tuple[str, int, int], str]:
    return {
        (b.code, c.number, v.number): v.text
        for b in result.books
        for c in b.chapters
        for v in c.verses
    }


def run_cross_check(
    doc: PdfDocument,
    layout: Layout,
    fixed: ParseResult,
    public: PublicWords,
    epub_path: Path,
    nlt_path: Path | None,
    skeleton: dict[tuple[str, int], int],
) -> CrossCheck:
    raw = parse_bible(doc, layout, Fixes.none(), public)
    solo = {
        f.name: _texts(
            parse_bible(doc, layout, dataclasses.replace(Fixes.none(), **{f.name: True}), public)
        )
        for f in dataclasses.fields(Fixes)
    }
    epub = parse_epub(epub_path, canonical_books(), skeleton)
    nlt = load_verses(nlt_path) if nlt_path is not None and nlt_path.is_file() else None
    absorbed = {
        (b.code, c.number, n)
        for b in fixed.books
        for c in b.chapters
        for v in c.verses
        for n in range(v.number + 1, v.last + 1)
    }
    pages: dict[int, list[str]] = {}
    for item in doc.items:
        if layout.bible_start <= item.page < layout.notes_start:
            pages.setdefault(item.page, []).append(item.text)
    return cross_check(
        fixed=_texts(fixed),
        raw=_texts(raw),
        solo=solo,
        epub=epub,
        nlt=nlt,
        absorbed=absorbed,
        pdf_headings={
            (b.code, c.number): [h.text for h in c.headings]
            for b in fixed.books
            for c in b.chapters
        },
        skeleton=skeleton,
        callout_labels=fixed.diagnostics.callout_labels,
        pages={page: " ".join(texts) for page, texts in pages.items()},
        spans={
            (b.code, c.number, v.number): v.pages
            for b in fixed.books
            for c in b.chapters
            for v in c.verses
        },
    )


def crosscheck_tsv(cross: CrossCheck, header: str = "book\tchapter\tverse") -> str:
    rows = [f"{header}\tclass\tdetail\tepub_damaged\tfixes"]
    for f in cross.findings:
        if f.verdict.value == "agree":
            continue
        book, chapter, verse = f.key
        rows.append(
            f"{book}\t{chapter}\t{verse}\t{f.verdict.value}\t{f.detail}\t"
            f"{int(f.epub_damaged)}\t{','.join(f.fixes)}"
        )
    rows += [f"{h.chapter[0]}\t{h.chapter[1]}\t\theading:{h.kind}\t\t\t" for h in cross.headings]
    return "\n".join(rows) + "\n"


def _dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def convert(pdf: Path, epub: Path | None, nlt: Path | None, out_dir: Path) -> tuple[bool, str]:
    """Run the converter; return (wrote output?, summary text)."""
    doc = parse_pdf_xml(run_pdftohtml(pdf))
    layout = find_layout(doc)
    public = PublicWords(load_public_texts())
    result = parse_bible(doc, layout, Fixes(), public)
    skeleton = load_skeleton()
    validation = validate(result, skeleton)
    cross = run_cross_check(doc, layout, result, public, epub, nlt, skeleton) if epub else None
    notes = build_notes(doc, layout, result, public, skeleton)
    notes_cross = cross_check_epub_notes(notes, epub, doc, layout, _texts(result)) if epub else None
    articles_cross = (
        cross_check_epub_articles(notes, epub, doc, layout, _texts(result)) if epub else None
    )
    features_cross = (
        cross_check_epub_features(notes, epub, doc, layout, _texts(result)) if epub else None
    )
    rights = copyright_lines(doc, layout)
    lines = summary(
        result, validation, cross, source=pdf.name, pages=doc.page_count,
        poppler=doc.producer_version,
    )  # fmt: skip
    lines += ["", *notes_summary(notes, notes_cross)]
    lines += ["", *articles_summary(notes, articles_cross)]
    lines += ["", *features_summary(notes, features_cross)]
    ok = (
        validation.ok
        and not result.diagnostics.unclassified
        and not result.diagnostics.errors
        and notes.ok
    )
    work = out_dir / "work" / CODE
    notes_file = out_dir / "notes" / f"{CODE}.json"
    if ok:
        work.mkdir(parents=True, exist_ok=True)
        notes_file.parent.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{CODE}.json").write_text(_dump(translation_payload(result, rights)), "utf-8")
        notes_file.write_text(_dump(notes_payload(notes, CODE)), "utf-8")
        (work / "markers.json").write_text(_dump(marker_payload(result.markers)), "utf-8")
        if cross is not None:
            (work / "crosscheck.tsv").write_text(crosscheck_tsv(cross), "utf-8")
        if notes_cross is not None:
            (work / "notes-crosscheck.tsv").write_text(
                crosscheck_tsv(notes_cross, "note\tchapter\toccurrence"), "utf-8"
            )
        if articles_cross is not None:
            (work / "articles-crosscheck.tsv").write_text(
                crosscheck_tsv(articles_cross, "article\tchapter\toccurrence"), "utf-8"
            )
        if features_cross is not None:
            (work / "topics-crosscheck.tsv").write_text(
                crosscheck_tsv(features_cross, "item\tchapter\toccurrence"), "utf-8"
            )
        lines += ["", f"Wrote {out_dir / f'{CODE}.json'}, {notes_file} and {work}/"]
    else:
        lines += ["", "Checks failed — nothing written."]
    text = "\n".join(lines) + "\n"
    if ok:
        (work / "summary.txt").write_text(text, "utf-8")
    return ok, text
