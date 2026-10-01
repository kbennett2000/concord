"""Validation, the EPUB witness and the cross-check classes (made-up text)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from bible_core.seed import load_canonical_books_text, parse_canonical_books
from emb_convert.crosscheck import Verdict, cross_check
from emb_convert.epub import BREAK, EpubBible, parse_epub
from emb_convert.validate import validate
from pdfxmlkit import body, header, heading, parse, start, vnum

GEN = start("GEN") + 1
Key = tuple[str, int, int]


def no_fused(_text: str) -> None:
    return None


# -- validation ---------------------------------------------------------------------------


def genesis(*verses: str) -> object:
    items = [*header("GEN", 1)]
    for n, number in enumerate(verses):
        items += [vnum(number, 100 + 20 * n), body(f"Verse {number} words.", 100 + 20 * n, 50)]
    return parse({GEN: items})


def test_sequence_matches_the_skeleton_with_combined_verses() -> None:
    check = validate(genesis("1", "2-3", "4"), {("GEN", 1): 4}, no_fused)  # type: ignore[arg-type]
    assert check.ok and check.absorbed == 1


def test_sequence_flags_an_unexpected_gap() -> None:
    check = validate(genesis("1", "2", "4"), {("GEN", 1): 4}, no_fused)  # type: ignore[arg-type]
    assert not check.ok and check.sequence == ["GEN 1: missing [3] extra []"]


def test_hygiene_flags_a_heading_fused_into_a_verse() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                heading("The Second Part", 90),
                vnum("1", 110),
                body("Words then The Second Part again.", 110, 50),
            ]
        }
    )
    check = validate(result, {("GEN", 1): 1}, no_fused)
    assert check.hygiene["fused-heading"] == ["GEN 1:1"]


# -- the EPUB witness -----------------------------------------------------------------------

CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""
OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0"><manifest>
<item id="a" href="OEBPS/a.html" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="a"/></spine></package>"""
PAGE = """<html><body>
<p><big>Genesis</big> <big><big>1</big></big></p>
<p><b><i>A Made-up Heading</i></b></p>
<p><a><sup><small>1</small></sup></a> First verse text.<a>*</a>
<sup><small>2</small></sup>Second verse, with a<a></a> gap.</p>
<div><b><img src="x.jpg"/><a href="z.html">A Callout</a></b></div>
<div><hr/><p>PERSPECTIVES</p><p>Box words.</p><hr/></div>
<p><sup><small>3</small></sup>Third  verse.</p>
<p><big>Psalm</big> <big>3</big></p><p><i>A made-up title.</i></p>
<p><sup><small>1</small></sup>Psalm words.</p>
</body></html>"""


def epub_file(tmp_path: Path) -> Path:
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("content.opf", OPF)
        archive.writestr("OEBPS/a.html", PAGE)
    return path


def test_epub_parse_reads_verses_headings_titles_and_skips_boxes_and_callouts(
    tmp_path: Path,
) -> None:
    seeds = parse_canonical_books(load_canonical_books_text())
    bible = parse_epub(epub_file(tmp_path), seeds, {("GEN", 1): 3, ("PSA", 3): 8})
    assert bible.verses[("GEN", 1, 1)] == "First verse text."
    assert bible.verses[("GEN", 1, 2)].replace(BREAK, "|") == "Second verse, with a| gap."
    assert bible.verses[("GEN", 1, 3)].replace(BREAK, "|") == "Third | verse."
    assert bible.verses[("PSA", 3, 1)] == "A made-up title. Psalm words."
    assert bible.headings[("GEN", 1)] == ["A Made-up Heading"]


# -- the cross-check classes -----------------------------------------------------------------


def classify(pdf: str, epub: str, *, raw: str | None = None, nlt: str | None = None) -> Verdict:
    key: Key = ("GEN", 1, 1)
    witness = EpubBible(verses={key: epub})
    result = cross_check(
        fixed={key: pdf},
        raw={key: raw if raw is not None else pdf},
        solo={},
        epub=witness,
        nlt={key: nlt} if nlt is not None else None,
        absorbed=set(),
        pdf_headings={},
        skeleton={("GEN", 1): 1},
        callout_labels=[],
        pages={10: "the words that the page prints around this verse"},
        spans={key: (10, 10)},
    )
    return result.findings[0].verdict


def test_agree_fixed_quirk_and_fix_regression() -> None:
    assert classify("a good day", "a good day") is Verdict.AGREE
    assert classify("a good day", "a good day", raw="a g o o d day") is Verdict.FIXED_QUIRK
    assert classify("a goodday", "a good day", raw="a good day") is Verdict.FIX_REGRESSION


def test_pdf_only_words_need_evidence_at_the_spot() -> None:
    plain = classify("he came to the city gate", "he came to the gate")
    assert plain is Verdict.OPEN  # how a leaked label or box line would surface
    broken = classify("he came to the city gate", f"he came to the {BREAK} gate")
    assert broken is Verdict.EPUB_LOSS
    fused = classify("he came to the city gate", "he came to thecitygat")
    assert fused is Verdict.EPUB_VISIBLE or fused is Verdict.EPUB_LOSS
    nlt = classify("he came to the city gate", "he came to the gate", nlt="to the city gate")
    assert nlt is Verdict.EPUB_LOSS


def test_epub_only_words_are_scraps_splices_or_open() -> None:
    assert classify("the words", 'the words width="0">') is Verdict.EPUB_VISIBLE
    assert classify("the words", "the zqxw words") is Verdict.EPUB_VISIBLE  # a non-word
    spliced = classify("words that the page", "words that page words the page")
    assert spliced is Verdict.EPUB_SPLICE  # real words, but not printed there on the PDF page
    on_page = classify("page the words that prints", "page the words that the page prints")
    assert on_page is Verdict.OPEN  # the PDF page does print it: maybe a dropped word


def test_hyphenation_variant() -> None:
    assert classify("a coworker came", "a co-worker came") is Verdict.SPELLING
