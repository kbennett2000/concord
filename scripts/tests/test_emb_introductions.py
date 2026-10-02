"""EMB's book introductions on synthetic pdftohtml XML (V8-S5b; made-up text and made-up images
only): every section form and its Markdown, the figure and its bytes, the links, the timeline,
what the text pass sets aside, the checks that block the write, and the EPUB witness."""

from __future__ import annotations

import dataclasses
import json
import zipfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from emb_convert.charts import find_charts
from emb_convert.clean import Fixes, PublicWords
from emb_convert.convert import stale_assets, translation_payload, write_assets
from emb_convert.epub import BREAK, IMAGE, EpubBible, parse_epub
from emb_convert.introductions import (
    EpubIntroductions,
    IntroductionFindings,
    build_introductions,
    cross_check_epub_introductions,
    documents_payload,
    head_order,
    key,
    read_figures,
)
from emb_convert.layout import canonical_books, find_layout
from emb_convert.notes import context
from emb_convert.pdfxml import PdfDocument, parse_pdf_xml
from emb_convert.skeleton import load_skeleton
from emb_convert.text import ParseResult, parse_bible
from imagekit import jpeg
from pdfxmlkit import (
    FEATURES_PAGE,
    Img,
    T,
    body,
    document,
    full,
    header,
    heading,
    nav,
    start,
    verse_texts,
    vnum,
)

HOME = start("GEN")  # the navigation page
INTRO = HOME + 1
CH = HOME + 3  # chapter 1's page
PUBLIC = ("zorbalit",)  # the word a label's glyph gap breaks
FIGURE = jpeg(1024, 170)

Pages = dict[int, list[T | Img]]

EXPECTED_WORDS = """WHAT IS THIS? Made-up words that run on to the right margin of
the page and end here. THE
PARTS PART 1: ZORBALIT (CHAPTERS 1–2) Chapters 1–2: Made-up beginnings Chapter 2: A
made-up end KEY THINGS One made-up thing Another made-up thing TIME IN MADE-UP UNITS TO
REMEMBER 1:2 A made-up poetic line, and another one. MADE-UP WORDS IN 1:1. Made-up prose
that the book quotes runs right to the margin of its column. A VIEW A MADE-UP SUB-HEAD.
Made-up words under the sub-head run to the margin, then stop short. A MADE-UP BOX LABEL
Genesis? A made-up point. BEGINNING FIRST (no date) 2000 B.C. SOMETHING HAPPENS 1900 A
MADE-UP EVENT LONG ENOUGH THAT IT RUNS ON 1800 ONE EVENT AND ANOTHER"""

EXPECTED = """## WHAT IS THIS?

Made-up words that run on to the right margin of the page and end here.

## THE PARTS

**PART 1: ZORBALIT ([CHAPTERS 1–2](ref:GEN.1-2))**

- [Chapters 1–2](ref:GEN.1-2): Made-up beginnings
- [Chapter 2](ref:GEN.2): A made-up end

## KEY THINGS

- One made-up thing
- Another made-up thing

## TIME

![IN MADE-UP UNITS](asset:reading-time-gen.jpg)

## TO REMEMBER

**[1:2](ref:GEN.1.2)**

> A made-up poetic line,\\
> and another one.

**MADE-UP WORDS IN [1:1](ref:GEN.1.1).**

> Made-up prose that the book quotes runs right to the margin of its column.

## A VIEW

**A MADE-UP SUB-HEAD.**

Made-up words under the sub-head run to the margin, then stop short.

## A MADE-UP BOX LABEL Genesis?

A made-up point.

- BEGINNING
- **FIRST (no date)**
- 2000 B.C.\\
  **SOMETHING HAPPENS**
- 1900\\
  **A MADE-UP EVENT LONG ENOUGH THAT IT RUNS ON**
- 1800\\
  **ONE EVENT**\\
  **AND ANOTHER**"""


def pages(figure: str, *, figure_page: int = INTRO, figure_top: int = 325) -> Pages:
    """Genesis: its navigation page, a two-page introduction (a callout line closing it), and
    chapters 1–2 — a heading above chapter 1, on its page."""
    given: Pages = {
        HOME: [T("Genesis", 54, 38, 15, bold=True), *nav("GEN", 2)],
        INTRO: [
            T("genesis", 57, 38, 23, bold=True),
            T("WHAT IS THIS?", 111, 38, bold=True),
            full("Made-up words that run on to the right margin of the page and", 125),
            T("end here.", 140),
            T("THE PARTS", 169, 38, bold=True),
            T("PART 1: ZORB ALIT (", 183, 38, 7, bold=True),
            T("CHAPTERS 1–2", 183, 114, 7, blue=True, bold=True, link=CH),
            T(")", 183, 169, 7, bold=True),
            T("Chapters 1–2", 197, 38, blue=True, link=CH),
            T(": Made-up beginnings", 197, 100),
            T("Chapter 2", 211, 38, blue=True, link=CH + 1),
            T(": A made-up end", 211, 90),
            T("KEY THINGS", 240, 38, bold=True),
            T("One made-up thing", 254),
            T("Another made-up thing", 268),
            T("TIME", 297, 38, bold=True),
            T("IN MADE-UP UNITS", 311, 38, 7),
            T("TO REMEMBER", 420, 38, bold=True),
            T("1:2", 434, 38, 9, blue=True, bold=True, link=CH),
            T("A made-up poetic line,", 445, 46),
            T("and another one.", 459, 46),
        ],
        INTRO + 1: [
            T("MADE-UP WORDS IN ", 40, 38, 9, bold=True),
            T("1:1", 40, 134, 9, blue=True, bold=True, link=CH),
            T(".", 40, 150, 9, bold=True),
            full("Made-up prose that the book quotes runs right to the margin of", 51, 61),
            T("its column.", 65, 61),
            T("A VIEW", 94, 38, bold=True),
            T("A MADE-UP SUB-HEAD.", 108, 38, 9, bold=True),
            full("Made-up words under the sub-head run to the margin, then", 119, 61),
            T("stop short.", 133, 61),
            T("A MADE-UP BOX LABEL", 180, 161, 7),
            T("Genesis?", 190, 179),
            T("+ + +", 216, 189),
            T("A made-up point.", 242, 78),
            T("BEGINNING", 289, 61, 9),
            T("FIRST (no date)", 314, 61, bold=True),
            T("2000 ", 343, 61, 9),
            T("B.C.", 344, 82, 7),
            T("SOMETHING HAPPENS", 354, 61, bold=True),
            T("1900", 383, 61, 9),
            T("A MADE-UP EVENT LONG ENOUGH THAT IT RUNS", 394, 61, bold=True, width=280),
            T("ON", 408, 61, bold=True),
            T("1800", 437, 61, 9),
            T("ONE EVENT", 448, 61, bold=True),
            T("AND ANOTHER", 462, 61, bold=True),
            T("Someone Made Up", 480, 250, blue=True, bold=True, link=FEATURES_PAGE + 1),
        ],
        CH: [
            heading("A Made-up Heading", 40),
            *header("GEN", 1, top=60),
            vnum("1", 100),
            body("A made-up first verse.", 100, 45),
            vnum("2", 120),
            body("A made-up second verse.", 120, 45),
        ],
        CH + 1: [*header("GEN", 2), vnum("1", 100), body("Chapter two opens.", 100, 45)],
    }
    given[figure_page] = [*given[figure_page], Img(figure_top, figure, 84, 303)]
    return given


def run(
    given: Mapping[int, Sequence[T | Img]],
) -> tuple[PdfDocument, ParseResult, IntroductionFindings]:
    doc = parse_pdf_xml(document(given))
    layout = find_layout(doc)
    region = find_charts(doc, layout)
    words = PublicWords(PUBLIC)
    result = parse_bible(doc, layout, Fixes(), words, region.images)
    figures, errors = read_figures(doc, layout)
    assert not errors
    ctx = context(doc, layout, result, words, load_skeleton())
    return doc, result, build_introductions(doc, layout, result, ctx, figures)


def _figure(tmp_path: Path) -> str:
    path = tmp_path / "figure.jpg"
    path.write_bytes(FIGURE)
    return str(path)


def _gen(found: IntroductionFindings) -> dict[str, object]:
    (gen,) = [d for d in found.documents if d["book"] == "GEN"]
    return gen


# --- the document ------------------------------------------------------------------------------


def test_an_introduction_becomes_a_document(tmp_path: Path) -> None:
    _, _, found = run(pages(_figure(tmp_path)))
    assert _gen(found) == {
        "slug": "introduction-gen",
        "kind": "book-introduction",
        "title": "Genesis",  # as the What's the Point line names it; the title line is lower case
        "book": "GEN",
        "ordinal": 1,
        "text": EXPECTED,
    }
    # the other 65 books have no introduction here
    assert len(found.errors) == 65 and all(e.endswith(": no introduction") for e in found.errors)


def test_its_figure_is_an_asset_byte_for_byte(tmp_path: Path) -> None:
    _, _, found = run(pages(_figure(tmp_path)))
    assert found.assets == {"reading-time-gen.jpg": FIGURE}
    assert len(found.figures) == 1 and not found.unclaimed
    assert found.captions["GEN"] == "IN MADE-UP UNITS"


def test_a_caption_on_the_page_before_its_figure(tmp_path: Path) -> None:
    """The caption closes its page; the figure opens the next, the rest following it."""
    given = pages(_figure(tmp_path))
    texts = [i for i in given[INTRO] if isinstance(i, T)]
    after = [i for i in texts if i.top > 311]
    moved = [dataclasses.replace(i, top=i.top - 420 + 130) for i in after]
    below = [dataclasses.replace(i, top=i.top + 160) for i in given[INTRO + 1]]
    given[INTRO] = [i for i in texts if i.top <= 311]
    given[INTRO + 1] = [Img(30, _figure(tmp_path), 84, 303), *moved, *below]  # type: ignore[list-item]
    _, _, found = run(given)
    assert _gen(found)["text"] == EXPECTED


def test_links_resolve_and_agree_with_the_books_targets(tmp_path: Path) -> None:
    _, _, found = run(pages(_figure(tmp_path)))
    assert [(f.link, f.targets, f.evidence) for f in found.links] == [
        ("CHAPTERS 1–2", ["GEN.1-2"], "agrees"),
        ("Chapters 1–2", ["GEN.1-2"], "agrees"),
        ("Chapter 2", ["GEN.2"], "agrees"),
        ("1:2", ["GEN.1.2"], "agrees"),
        ("1:1", ["GEN.1.1"], "agrees"),
    ]


def test_what_it_prints_by_kind(tmp_path: Path) -> None:
    _, _, found = run(pages(_figure(tmp_path)))
    built = found.structures
    assert (built["head"], built["point"], built["timeline"], found.timelines) == (6, 1, 1, 1)
    assert (built["list"], built["list items"], built["paragraph"]) == (2, 4, 2)
    assert (built["quotation labels"], built["sub-heads and other labels"]) == (2, 2)
    assert (built["quoted lines of poetry"], built["quoted paragraphs"]) == (2, 1)
    assert built["timeline entries"] == 5
    assert built["timeline events without a date"] == 1
    assert built["timeline dates without an event"] == 1
    assert built["timeline events on two lines"] == 2
    assert built["timeline events set on two lines, the first not wrapped"] == 1
    assert found.ornaments == 1
    assert found.fixes["letter-spaced"] == 1  # the label's broken word
    assert found.head_lists["GEN"] == [
        "WHAT IS THIS?", "THE PARTS", "KEY THINGS", "TIME", "TO REMEMBER", "A VIEW"
    ]  # fmt: skip
    assert found.words == {"GEN": len(EXPECTED_WORDS.split())}


def test_callouts_and_the_heading_over_chapter_1_are_set_aside(tmp_path: Path) -> None:
    _, result, found = run(pages(_figure(tmp_path)))
    assert (found.callouts_set_aside, found.set_aside) == (1, 1)
    assert found.callout_labels == {"GEN": ["Someone Made Up"]}
    chapter = result.books[0].chapters[0]
    assert [h.text for h in chapter.headings] == ["A Made-up Heading"]  # still S1's heading
    assert "Someone" not in str(_gen(found)["text"])


def test_the_text_pass_reads_the_same_verses_with_the_introduction(tmp_path: Path) -> None:
    with_intro = pages(_figure(tmp_path))
    without = {**with_intro, INTRO: [], INTRO + 1: []}
    _, a, _ = run(with_intro)
    _, b, _ = run(without)
    assert verse_texts(a) == verse_texts(b)
    assert translation_payload(a, "x") == translation_payload(b, "x")


def test_the_same_pdf_gives_byte_identical_documents(tmp_path: Path) -> None:
    given = pages(_figure(tmp_path))
    first = json.dumps(documents_payload(run(given)[2], "EMB"), ensure_ascii=False, indent=2)
    second = json.dumps(documents_payload(run(given)[2], "EMB"), ensure_ascii=False, indent=2)
    assert first == second


def test_the_heads_keep_one_order() -> None:
    order, out = head_order({"A": ["ONE", "TWO", "FOUR"], "B": ["ONE", "THREE", "FOUR"]})
    assert (order, out) == (["ONE", "THREE", "TWO", "FOUR"], [])
    assert head_order({"A": ["ONE", "TWO"], "B": ["TWO", "ONE"]})[1] == ["B"]


# --- what blocks the write ---------------------------------------------------------------------


def _without_figure(tmp_path: Path) -> Pages:
    given = pages(_figure(tmp_path))
    return {n: [i for i in items if not isinstance(i, Img)] for n, items in given.items()}


def test_no_figure_blocks(tmp_path: Path) -> None:
    _, _, found = run(_without_figure(tmp_path))
    assert "GEN: 0 figures in its introduction" in found.errors
    assert not found.ok


def test_two_figures_block(tmp_path: Path) -> None:
    given = pages(_figure(tmp_path))
    given[INTRO + 1] = [*given[INTRO + 1], Img(150, _figure(tmp_path), 84, 303)]
    _, _, found = run(given)
    assert "GEN: 2 figures in its introduction" in found.errors
    assert found.unclaimed and not found.ok


def test_a_line_the_layout_doesnt_explain_blocks(tmp_path: Path) -> None:
    given = pages(_figure(tmp_path))
    given[INTRO] = [*given[INTRO], T("A stray made-up line", 470, 200)]
    _, _, found = run(given)
    assert any("doesn't explain" in e for e in found.errors) and not found.ok


def test_an_unexplained_link_blocks(tmp_path: Path) -> None:
    given = pages(_figure(tmp_path))
    given[INTRO] = [
        T("Chapter 2", i.top, 38, blue=True, link=CH + 5) if isinstance(i, T)
        and i.text == "Chapter 2" else i
        for i in given[INTRO]
    ]  # fmt: skip
    _, _, found = run(given)
    assert [f.evidence for f in found.links if f.link == "Chapter 2"] == ["unexplained"]
    assert not found.ok


def test_a_stale_figure_blocks_and_a_written_one_does_not(tmp_path: Path) -> None:
    folder = tmp_path / "assets" / "EMB"
    _, _, found = run(pages(_figure(tmp_path)))
    write_assets(folder, found.assets)
    assert (folder / "reading-time-gen.jpg").read_bytes() == FIGURE
    assert stale_assets(folder, found.assets) == []
    (folder / "reading-time-exo.jpg").write_bytes(jpeg())
    assert stale_assets(folder, found.assets) == ["reading-time-exo.jpg"]


# --- the EPUB witness --------------------------------------------------------------------------


def _epub_blocks(found: IntroductionFindings) -> list[str]:
    """The introduction as the EPUB reader keeps it — the navigation rows, each section as
    printed (the caption apart, its image after it), the callout's label — from the PDF's own
    fixed text."""
    blocks = ["Introduction 1 2", "3"]
    for n in range(1, len(found.section_heads["GEN"]) + 1):
        text = found.texts[key("GEN", n)]
        if "IN MADE-UP UNITS" in text:
            blocks += [text.replace(" IN MADE-UP UNITS", ""), "IN MADE-UP UNITS", IMAGE]
        else:
            blocks.append(text)
    return [*blocks, "Someone Made Up"]


def _cross(
    tmp_path: Path, edit: Callable[[list[str]], list[str]] = lambda b: b
) -> tuple[dict[str, str], set[str], EpubIntroductions]:
    doc, result, found = run(pages(_figure(tmp_path)))
    epub = EpubBible(intros={"GEN": edit(_epub_blocks(found))})
    cross, witness = cross_check_epub_introductions(
        found, epub, doc, find_layout(doc), verse_texts(result)
    )
    verdicts = {f.key[0]: f.verdict.value for f in cross.findings}
    return verdicts, {k[0] for k in witness.damaged}, witness


def test_the_epub_agrees_section_by_section_and_witnesses_the_figure(tmp_path: Path) -> None:
    verdicts, damaged, witness = _cross(tmp_path)
    assert len(verdicts) == 7  # six heads and the What's the Point box
    # the label's broken word: the raw parse prints it apart, the EPUB whole, the fix agrees
    assert verdicts.pop("INTRO GEN §2") == "fixed-pdf-quirk"
    assert set(verdicts.values()) == {"agree"} and not damaged
    assert witness.figures == {"GEN": "under its caption"} and not witness.lost_heads


def test_a_word_the_epub_lacks_is_open_unless_visibly_damaged(tmp_path: Path) -> None:
    def swap(word: str) -> Callable[[list[str]], list[str]]:
        return lambda blocks: [b.replace("end here.", word) for b in blocks]

    verdicts, damaged, _ = _cross(tmp_path, swap("here."))  # a word the PDF prints, lost
    assert verdicts["INTRO GEN §1"] == "open" and not damaged
    verdicts, damaged, _ = _cross(tmp_path, swap(f"{BREAK} here."))  # lost at a visible break
    # still open, but in visibly damaged EPUB text: listed for reference, not a failure
    assert verdicts["INTRO GEN §1"] == "open" and damaged == {"INTRO GEN §1"}


def test_a_head_the_epub_lost_merges_its_section_into_the_one_before(tmp_path: Path) -> None:
    def lose(blocks: list[str]) -> list[str]:
        return [b.replace("KEY THINGS ", "") for b in blocks]

    verdicts, damaged, witness = _cross(tmp_path, lose)
    assert witness.lost_heads == ["GEN §3"]
    assert verdicts["INTRO GEN §3"] == "epub-damage-visible"  # missing in the EPUB
    assert "INTRO GEN §2" in damaged


def test_an_image_the_epub_turned_into_markup_is_named_so(tmp_path: Path) -> None:
    def scrap(blocks: list[str]) -> list[str]:
        return [('mg recindex="00001" alt="x"' if b == IMAGE else b) for b in blocks]

    assert _cross(tmp_path, scrap)[2].figures == {"GEN": "image markup damaged"}


CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""
OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0"><manifest>
<item id="a" href="OEBPS/a.html" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="a"/></spine></package>"""
BOOK = """<html><body>
<p><big>Genesis</big></p>
<p><a href="#i">Introduction</a> <a href="#c1">1</a> <a href="#c2">2</a></p>
<p><big><b>genesis</b></big></p>
<p><b>WHAT IS THIS?</b></p>
<p>Made-up words.</p>
<p><small>IN MADE-UP UNITS</small></p>
<p><img src="figure.jpg"/></p>
<p><b><i>A Made-up Heading</i></b></p>
<p><big>Genesis</big> <big>1</big></p>
<p><sup>1</sup> A made-up first verse.</p>
</body></html>"""


def test_the_epub_reader_keeps_each_introductions_blocks(tmp_path: Path) -> None:
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("content.opf", OPF)
        archive.writestr("OEBPS/a.html", BOOK)
    epub = parse_epub(path, canonical_books(), load_skeleton())
    assert epub.intros == {
        "GEN": ["Introduction 1 2", "WHAT IS THIS?", "Made-up words.", "IN MADE-UP UNITS", IMAGE]
    }  # the heading over chapter 1 (bold italic) is the text's, not kept
    assert epub.verses[("GEN", 1, 1)] == "A made-up first verse."
    assert epub.images == []  # an introduction's image isn't a chart's witness
