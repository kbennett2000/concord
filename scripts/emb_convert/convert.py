"""One run: PDF → parse → checks → (cross-check) → files under ``data/private/``.

Writes, only when every structural check passes:

- ``<out>/EMB.json`` — the translation (Concord's translation contract, code ``EMB``);
- ``<out>/notes/EMB.json`` — its textual and study notes, feature articles and charts (ADR-0011);
- ``<out>/documents/EMB.json`` — its 66 book introductions (ADR-0012, V8-S5b), then its front
  matter, reading plan and Personal Gold authors (V8-S5c), then the Verse Finder as printed
  (V8-S6b);
- ``<out>/topics/EMB.json`` — the Verse Finder as a topical source (ADR-0013, V8-S6b);
- ``<out>/assets/EMB/chart-NN.jpg`` — each chart's image as the PDF stores it (ADR-0012, V8-S4b);
- ``<out>/assets/EMB/reading-time-<book>.jpg`` — each introduction's figure, likewise (V8-S5b);
- ``<out>/work/EMB/markers.json`` — where each removed ``*`` sat (the textual notes' anchors);
- ``<out>/work/EMB/crosscheck.tsv`` — every verse cross-check finding by reference;
- ``<out>/work/EMB/notes-crosscheck.tsv`` — every note cross-check finding by note;
- ``<out>/work/EMB/articles-crosscheck.tsv`` — every article cross-check finding (V8-S3a);
- ``<out>/work/EMB/topics-crosscheck.tsv`` — every topic and box cross-check finding (V8-S3b);
- ``<out>/work/EMB/charts-crosscheck.tsv`` — each chart against the EPUB (V8-S4b);
- ``<out>/work/EMB/introductions-crosscheck.tsv`` — every introduction finding (V8-S5b);
- ``<out>/work/EMB/documents-crosscheck.tsv`` — every other document's finding (V8-S5c);
- ``<out>/work/EMB/verse-finder-crosscheck.tsv`` — every Verse Finder topic's finding (V8-S6b);
- ``<out>/work/EMB/summary.txt`` — the printed summary.

``work/`` is never scanned by a loader. The same PDF gives byte-identical files. The run
refuses to write when ``assets/EMB/`` holds a file it wouldn't write, so no stale image lingers.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from emb_convert.charts import find_charts
from emb_convert.clean import Fixes, PublicWords, collapse
from emb_convert.crosscheck import CrossCheck, cross_check
from emb_convert.documents import RESERVED, Witnessed, copyright_page, epub_cut, find_front
from emb_convert.documents import cross_check as cross_check_documents
from emb_convert.epub import parse_epub
from emb_convert.epub_charts import charts_tsv, cross_check_epub_charts
from emb_convert.epub_notes import read_runs
from emb_convert.frontmatter import build_front
from emb_convert.introductions import (
    build_introductions,
    cross_check_epub_introductions,
    documents_payload,
    read_figures,
)
from emb_convert.layout import Layout, canonical_books, find_layout
from emb_convert.lines import group_lines
from emb_convert.notes import (
    build_notes,
    context,
    cross_check_epub_articles,
    cross_check_epub_features,
    cross_check_epub_notes,
    notes_payload,
)
from emb_convert.pdfxml import PdfDocument, parse_pdf_xml, run_pdftohtml
from emb_convert.pgauthors import build_authors
from emb_convert.readingplan import PlanFindings, build_plan
from emb_convert.report import (
    articles_summary,
    charts_summary,
    documents_summary,
    features_summary,
    finder_summary,
    introductions_summary,
    notes_summary,
    summary,
)
from emb_convert.skeleton import load_public_texts, load_skeleton, load_verses
from emb_convert.text import Marker, ParseResult, parse_bible
from emb_convert.validate import validate
from emb_convert.versefinder import build_finder

CODE = "EMB"
NAME = "Every Man's Bible (NLT)"
LANGUAGE = "en"
PARAGRAPH_GAP = 13  # points between two lines of one paragraph on the copyright page


class ConvertError(Exception):
    """The run could not produce trustworthy output."""


def copyright_lines(doc: PdfDocument, layout: Layout) -> str:
    """The book's own rights lines, read from its copyright page at run time.

    Paragraphs of the first front-matter page that holds a "copyright ©", keeping those that
    end "All rights reserved." — not the photo credits, not the quotation credit-line
    templates ("Used by permission").
    """
    front = [i for i in doc.items if i.page < layout.bible_start]
    page = copyright_page(doc, layout)
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
        if RESERVED.search(text)
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


def stale_assets(assets_dir: Path, names: Iterable[str]) -> list[str]:
    """Files in ``assets_dir`` this run wouldn't write — any blocks the write (V8-S4b)."""
    keep = set(names)
    present = sorted(assets_dir.iterdir()) if assets_dir.is_dir() else []
    return [path.name for path in present if path.name not in keep]


def write_assets(assets_dir: Path, assets: dict[str, bytes]) -> None:
    """Each image exactly as the PDF stores it."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(assets.items()):
        (assets_dir / name).write_bytes(data)


def _dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def convert(pdf: Path, epub: Path | None, nlt: Path | None, out_dir: Path) -> tuple[bool, str]:
    """Run the converter; return (wrote output?, summary text)."""
    with tempfile.TemporaryDirectory(prefix="emb-convert-") as images:
        doc = parse_pdf_xml(run_pdftohtml(pdf, Path(images)))
        layout = find_layout(doc)
        charts = find_charts(doc, layout)  # reads each chart's bytes while the files exist
        figures, figure_errors = read_figures(doc, layout)  # and each introduction figure's
    public = PublicWords(load_public_texts())
    result = parse_bible(doc, layout, Fixes(), public, charts.images)
    skeleton = load_skeleton()
    validation = validate(result, skeleton)
    cross = run_cross_check(doc, layout, result, public, epub, nlt, skeleton) if epub else None
    notes = build_notes(doc, layout, result, public, skeleton, charts)
    notes_cross = cross_check_epub_notes(notes, epub, doc, layout, _texts(result)) if epub else None
    articles_cross = (
        cross_check_epub_articles(notes, epub, doc, layout, _texts(result)) if epub else None
    )
    features_cross = (
        cross_check_epub_features(notes, epub, doc, layout, _texts(result)) if epub else None
    )
    charts_cross = (
        cross_check_epub_charts(charts.charts, notes.charts.spots, epub, skeleton) if epub else None
    )
    ctx = context(doc, layout, result, public, skeleton)
    intros = build_introductions(doc, layout, result, ctx, figures)
    intros.errors += figure_errors
    intros_cross, intros_witness = (
        cross_check_epub_introductions(
            intros, parse_epub(epub, canonical_books(), skeleton), doc, layout, _texts(result)
        )
        if epub
        else (None, None)
    )
    front = find_front(doc, layout)
    front_matter = build_front(front, layout, ctx)
    plan = build_plan(front.plan, ctx) if front.plan is not None else PlanFindings()
    authors = build_authors(doc, layout, notes.articles.region, ctx)
    finder = build_finder(front.references, ctx)
    witnessed = Witnessed()
    for part in (front_matter.witnessed, plan.witnessed, authors.witnessed):
        witnessed.extend(part)
    flat = "".join(text for text, _ in read_runs(epub)) if epub else None
    epub_documents = epub_cut(flat, witnessed) if flat is not None else None
    documents_cross = (
        cross_check_documents(witnessed, epub_documents, doc, _texts(result))
        if epub_documents is not None
        else None
    )
    # the Verse Finder's own cut, so the other documents' findings stay as they were
    epub_finder = epub_cut(flat, finder.witnessed) if flat is not None else None
    finder_cross = (
        cross_check_documents(finder.witnessed, epub_finder, doc, _texts(result))
        if epub_finder is not None
        else None
    )
    documents = documents_payload(intros, CODE)
    documents["documents"] = [
        *intros.documents,
        *front_matter.documents,
        *(d for d in (plan.document, authors.document, finder.document) if d is not None),
    ]
    assets = {**notes.charts.assets, **intros.assets}
    assets_dir = out_dir / "assets" / CODE
    stale = stale_assets(assets_dir, assets)
    rights = copyright_lines(doc, layout)
    lines = summary(
        result, validation, cross, source=pdf.name, pages=doc.page_count,
        poppler=doc.producer_version,
    )  # fmt: skip
    lines += ["", *notes_summary(notes, notes_cross)]
    lines += ["", *articles_summary(notes, articles_cross)]
    lines += ["", *features_summary(notes, features_cross)]
    lines += ["", *charts_summary(notes, charts_cross, stale)]
    lines += ["", *introductions_summary(intros, intros_cross, intros_witness)]
    lines += ["", *documents_summary(front_matter, plan, authors, documents_cross, epub_documents)]
    lines += ["", *finder_summary(finder, finder_cross, epub_finder)]
    ok = (
        validation.ok
        and not result.diagnostics.unclassified
        and not result.diagnostics.errors
        and notes.ok
        and intros.ok
        and front_matter.ok
        and plan.ok
        and authors.ok
        and finder.ok
        and not stale
    )
    work = out_dir / "work" / CODE
    notes_file = out_dir / "notes" / f"{CODE}.json"
    documents_file = out_dir / "documents" / f"{CODE}.json"
    topics_file = out_dir / "topics" / f"{CODE}.json"
    if ok:
        work.mkdir(parents=True, exist_ok=True)
        notes_file.parent.mkdir(parents=True, exist_ok=True)
        documents_file.parent.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{CODE}.json").write_text(_dump(translation_payload(result, rights)), "utf-8")
        notes_file.write_text(_dump(notes_payload(notes, CODE)), "utf-8")
        documents_file.write_text(_dump(documents), "utf-8")
        topics_file.parent.mkdir(parents=True, exist_ok=True)
        topics_file.write_text(_dump(finder.payload), "utf-8")
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
        if charts_cross is not None:
            (work / "charts-crosscheck.tsv").write_text(charts_tsv(charts_cross), "utf-8")
        if intros_cross is not None:
            (work / "introductions-crosscheck.tsv").write_text(
                crosscheck_tsv(intros_cross, "introduction\tchapter\toccurrence"), "utf-8"
            )
        if documents_cross is not None:
            (work / "documents-crosscheck.tsv").write_text(
                crosscheck_tsv(documents_cross, "document\tchapter\toccurrence"), "utf-8"
            )
        if finder_cross is not None:
            (work / "verse-finder-crosscheck.tsv").write_text(
                crosscheck_tsv(finder_cross, "topic\tchapter\toccurrence"), "utf-8"
            )
        write_assets(assets_dir, assets)
        lines += [
            "",
            f"Wrote {out_dir / f'{CODE}.json'}, {notes_file}, {documents_file}, {topics_file}, "
            f"{assets_dir}/ and {work}/",
        ]
    else:
        lines += ["", "Checks failed — nothing written."]
    text = "\n".join(lines) + "\n"
    if ok:
        (work / "summary.txt").write_text(text, "utf-8")
    return ok, text
