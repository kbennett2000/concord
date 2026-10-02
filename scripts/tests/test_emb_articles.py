"""The feature articles on synthetic pdftohtml XML (V8-S3a; made-up text only): the index's
names, references, callouts and anchors, two-book passages, the Markdown blocks, link forms,
the sort among notes at one spot, and the EPUB witness."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from bible_core.loader import build_database
from bible_core.seed import load_canonical_books_text, parse_canonical_books
from emb_convert.articles import Article, parse_reference, shape
from emb_convert.clean import PublicWords, Vocabulary, fused_words, letter_spacing
from emb_convert.convert import translation_payload
from emb_convert.epub_articles import parse_epub_articles
from emb_convert.notes import notes_payload
from emb_convert.study import Part, resolve_run
from pdfxmlkit import (
    MWG_PAGE,
    PG_AUTHORS_PAGE,
    PG_PAGE,
    STUDY_NOTES_PAGE,
    SYSK_PAGE,
    T,
    body,
    callout_number,
    header,
    parse_notes,
    start,
    study_head,
    vnum,
)

GEN = start("GEN") + 1
EXO = start("EXO") + 1
BY_ALIAS = {a: s.id for s in parse_canonical_books(load_canonical_books_text()) for a in s.aliases}
LAST = {
    **{("EST", n): 20 for n in range(1, 11)},
    ("GEN", 1): 31,
    ("GEN", 2): 25,
    ("GEN", 3): 24,
    ("EXO", 1): 22,
}

MWG_ARTICLE = MWG_PAGE + 1
SYSK_ARTICLE = SYSK_PAGE + 1
PG_ARTICLE = PG_PAGE + 1


def callout(label: str, top: int, page: int) -> T:
    """A callout line: the article's index name, bold and blue, linking to its page."""
    return T(label, top, 250, blue=True, bold=True, link=page)


def wide(text: str, top: int, left: int = 38, **style: Any) -> T:
    """A justified line: it runs to the right margin."""
    return T(text, top, left, width=340 - left, **style)


GENESIS = [
    *header("GEN", 1),
    vnum("1", 100),
    body("First made-up verse.", 100, 45),
    vnum("2", 120),
    body("Second made-up verse.", 120, 45),
    vnum("3", 140),
    body("Third made-up verse.", 140, 45),
    callout("A Made-up Title", 165, MWG_ARTICLE),  # closes 1:2-3: the end of verse 3
    callout("Someone", 190, SYSK_ARTICLE),  # opens 1:4-5: the start of verse 4
    vnum("4", 215),
    body("Fourth made-up verse.", 215, 45),
    vnum("5", 235),
    body("Fifth made-up verse.", 235, 45),
]
GENESIS_2 = [*header("GEN", 2), vnum("1", 100), body("A second chapter's verse.", 100, 45)]
EXODUS = [*header("EXO", 1), vnum("1", 100), body("An exodus verse.", 100, 45)]

MWG_PAGES = {
    MWG_PAGE: [
        T("A Made-up Title", 100, 38, blue=True, link=MWG_ARTICLE),
        T(" . . . ", 100, 120),
        T("Genesis 1:2-3", 100, 150, blue=True, link=GEN),
        T("Two Books Here", 115, 38, blue=True, link=MWG_ARTICLE + 1),
        T(" . . . ", 115, 120),
        T("Genesis 2:1; Exodus 1:1", 115, 150, blue=True, link=GEN),
    ],
    MWG_ARTICLE: [
        T("A Made-up Title", 60, 100, 15, bold=True),
        T("Gen", 80, 150, 7, blue=True, link=GEN),
        T("esis 1:2-3", 80, 165, 7, blue=True, link=GEN),
        T("OPENING WORDS", 100, 38, bold=True, width=100),
        T(" run on across the whole line", 100, 138, width=202),
        T("and end here.", 115, 38, width=80),
        T("A second paragraph opens indented and runs", 130, 46, width=294),
        T("to its end ", 145, 38, width=60),
        T("2:1", 145, 98, blue=True, link=GEN + 1),
        T(".", 145, 115, width=5),
        T("“A quoted line,”", 170, 69, width=120),
        T("“and its reply.”", 185, 69, width=120),
        T("A list of short items:", 210, 38, width=120),
        T("First item.", 230, 61, width=80),
        T("Second item.", 245, 61, width=80),
        T("Third item.", 260, 61, width=80),
    ],
    MWG_ARTICLE + 1: [
        T("Two Books Here", 60, 100, 15, bold=True),
        T("Genesis 2:1; Exodus 1:1", 80, 150, 7, blue=True, link=GEN),
        T("WORDS ABOUT", 100, 38, bold=True, width=80),
        T(" two books.", 100, 118, width=80),
    ],
}
SYSK_PAGES = {
    SYSK_PAGE: [T("Someone", 100, 38, blue=True, link=SYSK_ARTICLE)],
    SYSK_ARTICLE: [
        T("made-up feature:", 40, 38, blue=True, link=SYSK_PAGE),
        T("someone", 40, 172, bold=True),
        T("Genesis 1:4-5", 54, 38, 7, blue=True, link=GEN),
        T("A HEAD", 78, 38, bold=True, width=60),
        T("LINE", 95, 38, 23, bold=True, width=60),
        T("A summary set off from the rest of the article.", 130, 61, width=279),
        T("MOST DAYS,", 170, 38, bold=True, width=80),
        T(" the made-up man kept on and on and on.", 170, 118, width=222),
        T("1. ", 190, 46, width=12),
        T("A lead that is italic.", 190, 58, italic=True, width=120),
        T("Its own paragraph opens deep and runs on to", 205, 78, width=262),
        T("the margin, then wraps.", 220, 61, width=120),
        T("2. ", 240, 46, width=12),
        T("Another lead.", 240, 58, italic=True, width=80),
        T("Sing a made-up line,", 270, 46, italic=True, width=120),
        T("and sing another.", 285, 46, italic=True, width=110),
        T("Pride. ", 310, 61, italic=True, width=40),
        T("A hanging item that runs on to the right margin", 310, 101, width=239),
        T("and wraps deep.", 325, 79, width=90),
        T("Envy. ", 340, 61, italic=True, width=40),
        T("A second hanging item.", 340, 101, width=140),
        T("A last paragraph with a source note.", 360, 46, width=200),
        T("1", 360, 246, 7, blue=True, link=SYSK_ARTICLE, width=4),
        T("1", 395, 38, 7, blue=True, link=SYSK_ARTICLE, width=4),
        T("  A made-up source, 1999.", 397, 41, 9, width=150),
        T("IN SHORT: A closing line.", 430, 100, bold=True, width=160),
    ],
}
PG_PAGES = {
    PG_AUTHORS_PAGE: [
        T("Some Author", 90, 38, 9, blue=True, bold=True, link=PG_ARTICLE),
        T(" wrote made-up books.", 88, 100, width=150),
    ],
    PG_PAGE: [
        T("A Caps Title", 90, 38, 9, blue=True, bold=True, link=PG_ARTICLE),
        T("Some Author", 100, 61),
        T("Some Author, A Made-up Book (1999), p. 1.", 126, 61),
    ],
    PG_ARTICLE: [
        T("Personal Gold", 60, 117, 23, blue=True, bold=True, link=PG_PAGE),
        T("from", 85, 86, 15, bold=True, italic=True),
        T("SOME AUTHOR", 85, 117, 15, blue=True, bold=True, link=PG_AUTHORS_PAGE),
        T("Genesis 1:1", 105, 150, blue=True, link=GEN),
        T("A CAPS TITLE", 130, 38, 15, bold=True),
        T("An epigraph in italics, set off.", 150, 61, italic=True, width=180),
        T("The text of the made-up article.", 175, 38, width=180),
    ],
}


def document() -> dict[int, list[T]]:
    return {GEN: GENESIS, GEN + 1: GENESIS_2, EXO: EXODUS, **MWG_PAGES, **SYSK_PAGES, **PG_PAGES}


def articles_of(notes: Any) -> list[dict[str, Any]]:
    return [n for n in notes.payload if n["type"] == "article"]


def by_title(notes: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for note in articles_of(notes):
        out.setdefault(note["title"], []).append(note)
    return out


# -- references and shapes ---------------------------------------------------------------------


def test_a_printed_passage_gives_its_parts_in_each_book() -> None:
    def parts(text: str) -> list[tuple[str, Part]] | str:
        return parse_reference(text, BY_ALIAS, LAST)

    assert parts("Genesis 1:27 and 2:15-25") == [
        ("GEN", Part(1, 27, 1, 27)),
        ("GEN", Part(2, 15, 2, 25)),
    ]
    assert parts("Genesis 1 and chapter 2") == [
        ("GEN", Part(1, 1, 1, 31)),
        ("GEN", Part(2, 1, 2, 25)),
    ]
    assert parts("Genesis 1–2") == [("GEN", Part(1, 1, 2, 25))]
    assert parts("Genesis 2:1; Exodus 1:1") == [
        ("GEN", Part(2, 1, 2, 1)),
        ("EXO", Part(1, 1, 1, 1)),
    ]
    assert parts("Book of Esther") == [("EST", Part(1, 1, 10, 20))]
    assert isinstance(parts("Nowhere 1:1"), str)


def test_shapes() -> None:
    def kind(text: str) -> str:
        found = parse_reference(text, BY_ALIAS, LAST)
        assert not isinstance(found, str)
        return shape(Article(None, 1, "", text, found, []), LAST)  # type: ignore[arg-type]

    assert kind("Genesis 1:2") == "verse"
    assert kind("Genesis 1:2-5") == "range"
    assert kind("Genesis 1") == "whole chapter"
    assert kind("Genesis 1–2") == "whole chapters"
    assert kind("Genesis 1:30–2:3") == "cross-chapter"
    assert kind("Genesis 1:2 and 2:3") == "multi-part"
    assert kind("Genesis 2:1; Exodus 1:1") == "two books"
    assert kind("Book of Esther") == "whole book"


# -- the articles, their callouts and anchors --------------------------------------------------


def test_articles_take_their_index_names_and_anchor_where_the_book_calls_them_out() -> None:
    parse, notes = parse_notes(document())
    assert notes.articles.ok, (notes.articles.errors, notes.articles.hygiene)
    found = by_title(notes)
    verses = {(v.number): v.text for v in parse.books[0].chapters[0].verses}
    mwg = found["A Made-up Title"][0]
    assert (mwg["book"], mwg["chapter"], mwg["verse"]) == ("GEN", 1, 3)
    assert mwg["char_offset"] == len(verses[3])  # after the verse: the line closes the passage
    assert mwg["label"] == "Men, Women, and God"
    assert mwg["passages"] == [
        {"start_chapter": 1, "start_verse": 2, "end_chapter": 1, "end_verse": 3}
    ]
    sysk = found["Someone"][0]
    assert (sysk["chapter"], sysk["verse"], sysk["char_offset"]) == (1, 4, 0)  # opens 1:4-5
    pg = found["A Caps Title"][0]  # never called out: the start of its first passage
    assert (pg["chapter"], pg["verse"], pg["char_offset"]) == (1, 1, 0)
    assert "passages" not in pg  # the single verse it anchors at (S2b's rule)
    two = found["Two Books Here"][0]  # never called out: its first passage, in Genesis
    assert (two["book"], two["chapter"], two["verse"]) == ("GEN", 2, 1)
    assert two["cross_references"] == [
        {"book": "EXO", "chapter": 1, "verse_start": 1, "verse_end": 1}
    ]
    assert notes.articles.region.m_breaks == 0


def test_a_callout_names_its_article_by_the_index_or_by_its_page() -> None:
    _, notes = parse_notes(document())
    region = notes.articles.region
    assert not region.unmatched_callouts
    assert [len(a.callouts) for a in region.articles] == [1, 0, 1, 0]
    assert region.authors == 1
    assert [len(e.credit) for e in region.entries["PG"]] == [2]


# -- the text --------------------------------------------------------------------------------


def test_the_body_becomes_markdown_blocks() -> None:
    _, notes = parse_notes(document())
    found = by_title(notes)
    mwg = found["A Made-up Title"][0]["text"]
    assert mwg.split("\n\n") == [
        "**OPENING WORDS** run on across the whole line and end here.",
        "A second paragraph opens indented and runs to its end [2:1](ref:GEN.2.1).",
        "> “A quoted line,”\n>\n> “and its reply.”",
        "A list of short items:",
        "- First item.\n- Second item.\n- Third item.",
    ]
    sysk = found["Someone"][0]["text"]
    assert sysk.split("\n\n") == [
        "## A HEAD LINE",
        "> A summary set off from the rest of the article.",
        "**MOST DAYS**, the made-up man kept on and on and on.",
        "1. *A lead that is italic*.",
        "   Its own paragraph opens deep and runs on to the margin, then wraps.",
        "2. *Another lead*.",
        "> *Sing a made-up line*,\\\n> *and sing another*.",
        "- *Pride*. A hanging item that runs on to the right margin and wraps deep.\n"
        "- *Envy*. A second hanging item.",
        "A last paragraph with a source note.¹",
        "¹ A made-up source, 1999.",
        "**IN SHORT: A closing line**.",
    ]
    pg = found["A Caps Title"][0]
    assert pg["text"].split("\n\n") == [
        "*from* Some Author",
        "> *An epigraph in italics, set off*.",
        "The text of the made-up article.",
    ]
    assert pg["label"] == "Personal Gold" and pg["text_format"] == "markdown"
    counts = notes.articles.structures["SYSK"]
    assert counts["numbered items"] == 2 and counts["numbered items with paragraphs"] == 1
    assert counts["poetry"] == 1 and counts["source note"] == 1 and counts["closing line"] == 1
    assert notes.articles.footnotes == 2


def test_articles_show_first_or_last_at_their_verse_without_renumbering_its_notes(
    tmp_path: Path,
) -> None:
    pages = document()
    pages[GEN] = [*GENESIS]
    pages[GEN][pages[GEN].index(vnum("4", 215))] = callout_number("4", 217)
    pages[STUDY_NOTES_PAGE] = [
        *study_head("Gen.", "1:4", 60, GEN),
        T(" A made-up study note.", 80, 38),
    ]
    result, notes = parse_notes(pages)
    data, notes_dir = tmp_path / "data", tmp_path / "notes"
    data.mkdir()
    notes_dir.mkdir()
    (data / "EMB.json").write_text(json.dumps(translation_payload(result, "Rights.")), "utf-8")
    (notes_dir / "EMB.json").write_text(json.dumps(notes_payload(notes, "EMB")), "utf-8")
    build_database(tmp_path / "bible.db", [data], notes_dirs=[notes_dir])
    with sqlite3.connect(tmp_path / "bible.db") as conn:
        rows = conn.execute(
            "SELECT verse, note_type, ordinal FROM translator_notes "
            "WHERE chapter = 1 AND verse = 4 ORDER BY verse, ordinal, id"
        ).fetchall()
    # the article opening 1:4 shows first; the study note keeps the number it had alone
    assert rows == [(4, "article", 0), (4, "sn", 1)]


# -- the joiners and link forms articles need ----------------------------------------------------


def vocabulary(*texts: str) -> Vocabulary:
    public = (
        " ".join(["why and pain could couldn’t don’t what it is"] * 25),
        *texts,
    )
    return Vocabulary(PublicWords(public), texts)


def test_words_the_italic_font_ran_together_split() -> None:
    words = vocabulary()
    assert fused_words("and then what?It is", words) == ("and then what? It is", 1)
    assert fused_words("why andpain", words) == ("why and pain", 1)
    assert fused_words("Idon’t", words) == ("I don’t", 1)
    assert fused_words("restate", words) == ("restate", 0)  # "re" is no word of its own


def test_after_a_k_a_no_word_rest_joins_where_the_italic_k_break_does() -> None:
    words = vocabulary("the work is done")
    joined = letter_spacing("a Fork elsom here", words, whole_item=True, k_breaks=True)
    assert joined == "a Forkelsom here"
    assert letter_spacing("a Fork elsom here", words, whole_item=True) is None


def test_link_forms_the_articles_print() -> None:
    names = {s.id: s.name for s in parse_canonical_books(load_canonical_books_text())}

    def targets(text: str, chapter: int | None = None) -> list[str] | str:
        refs = resolve_run(
            text,
            note_book="GEN",
            continues=None,
            page_book=None,
            by_alias=BY_ALIAS,
            names=names,
            note_chapter=chapter,
        )
        return refs if isinstance(refs, str) else [p.target for p in refs.parts]

    assert targets("v. 25", 24) == ["GEN.24.25"]
    assert targets("vv. 3, 5", 2) == ["GEN.2.3", "GEN.2.5"]
    assert isinstance(targets("v. 25"), str)  # no chapter to read it in
    assert targets("ch. 5") == ["GEN.5"]
    assert targets("2:15ff") == ["GEN.2.15"]
    assert targets("Exodus 1:3, Leviticus 2:4") == ["EXO.1.3", "LEV.2.4"]


# -- the EPUB witness --------------------------------------------------------------------------

CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""
OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0"><manifest>
<item id="a" href="OEBPS/a.html" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="a"/></spine></package>"""
PAGE = """<html><body>
<p><b>MEN, WOMEN, AND GOD INDEX</b></p><p><a>A Made-up Title</a> . . . Genesis 1:2-3</p>
<p><img src="x.jpg"/><br/><b>A Made-up Title</b><br/>Genesis 1:2-3<br/>
<b>OPENING WORDS</b> run on across the whole line and end here.</p>
<p><img src="x.jpg"/><br/><b>Two Books Here</b><br/>Genesis 2:1; Exodus 1:1<br/>
<b>WORDS ABOUT</b> two books.</p>
<p><b>SOMEONE YOU SHOULD KNOW INDEX</b></p>
</body></html>"""


def test_epub_articles_are_found_in_order_and_keyed_by_passage(tmp_path: Path) -> None:
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("content.opf", OPF)
        archive.writestr("OEBPS/a.html", PAGE)
    _, notes = parse_notes(document())
    mwg = [(key, a) for key, a in notes.articles.order if a.feature.key == "MWG"]
    found = parse_epub_articles(path, mwg)
    assert found.texts == {
        ("MWG Genesis 1:2-3", 0, 1): "OPENING WORDS run on across the whole line and end here.",
        ("MWG Genesis 2:1; Exodus 1:1", 0, 1): "WORDS ABOUT two books.",
    }
    assert not found.damaged and not found.missing
