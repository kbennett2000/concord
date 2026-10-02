"""What the Bible Says About topics and Perspectives boxes on synthetic pdftohtml XML (V8-S3b;
made-up text only): the topics' index, heads, subheads, quotations and references, callouts and
anchors; the boxes' parts, anchors and index; the quotation classes; the order at a shared
spot; and the EPUB witnesses."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from bible_core.loader import build_database
from emb_convert.clean import fused_sentences
from emb_convert.convert import translation_payload
from emb_convert.epub_articles import parse_epub_boxes, parse_epub_topics
from emb_convert.notes import notes_payload
from emb_convert.quotes import QuoteClass, classify
from pdfxmlkit import MWG_PAGE, PERSP_PAGE, WBSA_PAGE, T, body, header, parse_notes, start, vnum

GEN = start("GEN") + 1
EXO = start("EXO") + 1
TOPIC = WBSA_PAGE + 1
TOPIC_2 = WBSA_PAGE + 3
MWG_ARTICLE = MWG_PAGE + 1
PUBLIC = ("qz " * 30,)  # "Q. Z." must not read as a broken "qz"

V1 = "A poetic line, a long poetic line that runs to the margin and wraps back."
V2 = "Second made-up verse that runs on to the end."
V3 = "A stanza after a gap."
V5 = "Fifth made-up verse, quoted in a box."


def wide(text: str, top: int, left: int = 38, **style: Any) -> T:
    """A justified line: it runs to the right margin."""
    return T(text, top, left, width=340 - left, **style)


def callout(label: str, top: int, page: int) -> T:
    return T(label, top, 250, blue=True, bold=True, link=page)


def box(top: int, quote: str, reference: str, attribution: list[T]) -> list[T]:
    """A Perspectives box: label, its quotation of the passage, the reference, a saying, the
    attribution."""
    return [
        T("PERSPECTIVES", top, 61, 9, blue=True, link=PERSP_PAGE),
        T(quote, top + 25, 61, width=200),
        T(reference, top + 50, 61, 7, blue=True, link=GEN),
        T("A made-up saying,", top + 75, 61, width=120),
        T("on two short lines.", top + 90, 61, width=130),
        *attribution,
    ]


GENESIS = [
    *header("GEN", 1),
    vnum("1", 100),
    body(V1, 100, 45),
    vnum("2", 120),
    body(V2, 120, 45),
    callout("Patience", 145, TOPIC),  # after verse 2: the end of 1:2
    vnum("3", 170),
    body(V3, 170, 45),
    *box(
        195,
        V3,
        "GENESIS 1:3",
        [
            T("Q. Z. SOMEONE (1900–1950), 12TH ", 300, 61, 7, width=150),
            T("MADE-UP BOOK", 300, 211, 7, italic=True, width=60),
        ],
    ),
    vnum("4", 330),
    body("Fourth made-up", 330, 45),
    *box(
        355,
        "A poetic line . . . to the end.",
        "GENESIS 1:1; 1:2",
        [T("ANOTHER ONE", 460, 61, 7, width=80)],
    ),
    body("verse.", 490, 38),  # verse 4 goes on after the box
]
GENESIS_2 = [
    *header("GEN", 2),
    vnum("1", 100),
    body(V5, 100, 45),
]
EXODUS = [*header("EXO", 1), vnum("1", 100), body("An exodus verse.", 100, 45)]


def reference(top: int, *parts: tuple[str, int | None]) -> list[T]:
    """A right-aligned "(reference)" line: each part a linked reference or words between."""
    items = [T("(", top, 250, 9)]
    left = 252
    for text, page in parts:
        items.append(T(text, top, left, 9, blue=page is not None, link=page))
        left += len(text) * 5
    items.append(T(")", top, 338, 9))
    return items


WBSA_PAGES = {
    WBSA_PAGE: [
        T("MADE-UP FEATURE . . . INDEX", 54, 40, 15, blue=True, bold=True, link=WBSA_PAGE),
        T("Patience", 72, 38, blue=True, link=TOPIC),
        T("Rest, The", 86, 38, blue=True, link=TOPIC_2),
    ],
    TOPIC: [
        T("What the Bible Says about", 63, 38, 15, blue=True, bold=True, link=WBSA_PAGE),
        T("patience", 57, 214, 23, bold=True),
        T("A MADE-UP SUBHEAD", 97, 38, 9, bold=True),
        wide("Second made-up verse that runs on to", 107),
        T("the end.", 122, 38, width=40),
        *reference(150, ("Genesis 1:2", GEN)),
        T("A SECOND SUBHEAD THAT", 176, 38, 9, bold=True),
        T("WRAPS", 186, 38, 9, bold=True),
        T("A poetic line,", 196, 46, width=70),
        wide("a long poetic line that runs to the margin and", 211, 46),
        T("wraps back.", 225, 38, width=60),
        T("A stanza after a gap.", 260, 46, width=110),
        *reference(275, ("Genesis 1:1", GEN), ("; ", None), ("1:3", GEN)),
        T("A THIRD SUBHEAD", 300, 38, 9, bold=True),
        T("[Someone:] Fourth made-up verse.", 311, 38, width=170),
        *reference(325, ("Genesis 1:4", GEN), ("; compare ", None), ("Exodus 1:1", EXO)),
    ],
    TOPIC_2: [
        T("What the Bible Says about", 63, 38, 15, blue=True, bold=True, link=WBSA_PAGE),
        T("the rest", 57, 214, 23, bold=True),
        T("ONE SUBHEAD", 97, 38, 9, bold=True),
        T("Fifth made-up verse . . . in a box.", 107, 38, width=180),
        *reference(122, ("Genesis 2:1", GEN + 1)),
    ],
}
PERSP_PAGES = {
    PERSP_PAGE: [
        T("Someone", 72, 38, blue=True, link=GEN),
        T(" . . . ", 72, 100, link=GEN),
        T("Genesis 1:3", 72, 130, blue=True, link=GEN),
        T("Another One", 86, 38, blue=True, link=GEN),
        T(" . . . ", 86, 100, link=GEN),
        T("Genesis 1:1; 1:2", 86, 130, blue=True, link=GEN),
    ],
}


def document() -> dict[int, list[T]]:
    return {GEN: GENESIS, GEN + 1: GENESIS_2, EXO: EXODUS, **WBSA_PAGES, **PERSP_PAGES}


def featured(notes: Any, label: str) -> list[dict[str, Any]]:
    return [n for n in notes.payload if n.get("label") == label]


# -- the topics --------------------------------------------------------------------------------


def test_a_topic_becomes_markdown_with_its_references_as_links() -> None:
    _, notes = parse_notes(document(), PUBLIC)
    found = notes.features
    assert found.ok, (found.errors, found.topics.errors, found.hygiene, found.unreviewed)
    topic = featured(notes, "What the Bible Says About")[0]
    assert topic["text"].split("\n\n") == [
        "### A MADE-UP SUBHEAD",
        "Second made-up verse that runs on to the end.\\\n([Genesis 1:2](ref:GEN.1.2))",
        "### A SECOND SUBHEAD THAT WRAPS",
        "A poetic line,\\\na long poetic line that runs to the margin and wraps back.",
        "A stanza after a gap.\\\n([Genesis 1:1](ref:GEN.1.1); [1:3](ref:GEN.1.3))",
        "### A THIRD SUBHEAD",
        "\\[Someone:\\] Fourth made-up verse.\\\n"
        "([Genesis 1:4](ref:GEN.1.4); compare [Exodus 1:1](ref:EXO.1.1))",
    ]
    assert topic["text_format"] == "markdown"
    assert found.structures["WBSA"]["subheads"] == 4  # the wrapped one counts once
    # five quoted references, one linked but not quoted; two lines carry two
    assert (found.quoted, found.pointers, found.two_references) == (5, 1, 2)


def test_topics_take_index_names_and_anchor_at_their_callout() -> None:
    parse, notes = parse_notes(document(), PUBLIC)
    verses = {v.number: v.text for v in parse.books[0].chapters[0].verses}
    first, second = featured(notes, "What the Bible Says About")
    assert (first["book"], first["chapter"], first["verse"]) == ("GEN", 1, 2)
    assert first["char_offset"] == len(verses[2])  # after the verse the callout follows
    assert first["title"] == "Patience" and "ordinal" not in first
    assert "passages" not in first and "cross_references" not in first
    # never called out: the start of its first quoted verse, shown first there
    assert (second["chapter"], second["verse"], second["char_offset"]) == (2, 1, 0)
    # the index puts "The" last, for sorting; the title reads in normal order (V8-S5b)
    assert second["title"] == "The Rest" and second["ordinal"] == 0
    region = notes.features.topics
    assert [t.number for t in region.renamed] == [2]
    assert [len(t.callouts) for t in region.topics] == [1, 0]
    assert notes.features.anchors["WBSA", "end of a verse it quotes"] == 1
    assert notes.features.anchors["WBSA", "never called out"] == 1


def test_quotations_are_classed_against_the_verse_text() -> None:
    verse = "Then the made-up man said, “Wait for it.” And he waited."
    assert classify(verse, verse) is QuoteClass.IDENTICAL
    assert classify("then the made-up man said, Wait for it. And he waited", verse) is (
        QuoteClass.SAME_WORDS
    )
    assert classify("[Someone:] “Wait for it.”", verse) is QuoteClass.PART
    assert classify("The made-up man said, . . . And he waited.", verse) is QuoteClass.JOINED
    assert classify("The made-up man said, “Wait for it.” And [a name] waited.", verse) is (
        QuoteClass.JOINED
    )
    assert classify("The made-up man said, and he waited.", verse) is QuoteClass.OTHER


def test_an_edit_the_converter_has_not_reviewed_fails_the_run() -> None:
    pages = document()
    pages[TOPIC_2] = [
        *WBSA_PAGES[TOPIC_2][:3],
        T("Fifth made-up words, edited.", 107, 38, width=180),
        *reference(122, ("Genesis 2:1", GEN + 1)),
    ]
    _, notes = parse_notes(pages, PUBLIC)
    assert notes.features.unreviewed == ["WBSA 2 Genesis 2:1"]
    assert not notes.ok


def test_a_sentence_run_into_the_next_is_split() -> None:
    assert fused_sentences("plim vosk drane.Telo wint") == ("plim vosk drane. Telo wint", 1)
    assert fused_sentences("in 500 B.C. Then") == ("in 500 B.C. Then", 0)


# -- the boxes ---------------------------------------------------------------------------------


def test_boxes_split_into_their_parts_and_anchor_where_they_stand() -> None:
    parse, notes = parse_notes(document(), PUBLIC)
    found = notes.features
    assert found.ok, (found.errors, found.boxes.errors, found.hygiene)
    verses = {v.number: v.text for v in parse.books[0].chapters[0].verses}
    first, second = featured(notes, "Perspectives")
    assert (first["chapter"], first["verse"], first["char_offset"]) == (1, 3, len(verses[3]))
    assert "title" not in first and "passages" not in first  # its one verse is its anchor
    assert first["text"].split("\n\n") == [
        f"{V3}\\\n[GENESIS 1:3](ref:GEN.1.3)",
        "A made-up saying,\\\non two short lines.",
        "Q. Z. SOMEONE (1900–1950), 12TH *MADE-UP BOOK*",
    ]
    # inside verse 4, after its passage: the end of 1:4, both parts as passages
    assert (second["chapter"], second["verse"], second["char_offset"]) == (1, 4, len(verses[4]))
    assert second["passages"] == [
        {"start_chapter": 1, "start_verse": 1, "end_chapter": 1, "end_verse": 1},
        {"start_chapter": 1, "start_verse": 2, "end_chapter": 1, "end_verse": 2},
    ]
    assert found.outside == found.mid_verse == ["PERSP Genesis 1:1; 1:2 (at GEN 1:4)"]
    assert verses[4] == "Fourth made-up verse."  # the box is never verse text
    classes = found.classes["PERSP"]
    assert classes[QuoteClass.IDENTICAL.value] == 1 and classes[QuoteClass.JOINED.value] == 1
    assert [b.entry.name if b.entry else "" for b in found.boxes.boxes] == [
        "Someone",
        "Another One",
    ]


def test_a_box_whose_index_prints_another_passage_is_listed() -> None:
    pages = document()
    pages[PERSP_PAGE] = [*PERSP_PAGES[PERSP_PAGE][:5], T("Genesis 1:1-2", 86, 130, blue=True)]
    _, notes = parse_notes(pages, PUBLIC)
    assert [b.name for b in notes.features.unexplained_index] == ["PERSP Genesis 1:1; 1:2"]
    assert not notes.features.ok


# -- the order at a shared spot ----------------------------------------------------------------

MWG_PAGES = {
    MWG_PAGE: [
        T("A Made-up Title", 100, 38, blue=True, link=MWG_ARTICLE),
        T(" . . . ", 100, 120),
        T("Genesis 1:2", 100, 150, blue=True, link=GEN),
    ],
    MWG_ARTICLE: [
        T("A Made-up Title", 60, 100, 15, bold=True),
        T("Genesis 1:2", 80, 150, 7, blue=True, link=GEN),
        T("OPENING WORDS", 100, 38, bold=True, width=100),
        T(" of a made-up article.", 100, 138, width=150),
    ],
}


def test_a_topic_printed_above_an_earlier_article_shows_first_without_renumbering(
    tmp_path: Path,
) -> None:
    pages = {**document(), **MWG_PAGES}
    genesis = [*GENESIS]
    genesis.insert(genesis.index(callout("Patience", 145, TOPIC)) + 1, callout("Article", 157, 0))
    genesis[genesis.index(callout("Article", 157, 0))] = callout(
        "A Made-up Title", 157, MWG_ARTICLE
    )
    pages[GEN] = genesis
    result, notes = parse_notes(pages, PUBLIC)
    assert notes.features.shown_first == ["GEN 1:2 (ordinal 0)"]
    data, notes_dir = tmp_path / "data", tmp_path / "notes"
    data.mkdir()
    notes_dir.mkdir()
    (data / "EMB.json").write_text(json.dumps(translation_payload(result, "Rights.")), "utf-8")
    (notes_dir / "EMB.json").write_text(json.dumps(notes_payload(notes, "EMB")), "utf-8")
    build_database(tmp_path / "bible.db", [data], notes_dirs=[notes_dir])
    with sqlite3.connect(tmp_path / "bible.db") as conn:
        rows = conn.execute(
            "SELECT label, ordinal FROM translator_notes "
            "WHERE chapter = 1 AND verse = 2 ORDER BY verse, ordinal, id"
        ).fetchall()
    # the topic's callout line stands above the article's: it shows first, and the article
    # keeps the number it has without the topic
    assert rows == [("What the Bible Says About", 0), ("Men, Women, and God", 1)]


# -- the EPUB witnesses ------------------------------------------------------------------------

CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""
OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0"><manifest>
<item id="a" href="OEBPS/a.html" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="a"/></spine></package>"""
PAGE = """<html><body>
<p><big>Genesis</big> <big>1</big></p>
<p><sup>1</sup> A poetic line.</p>
<p><sup>3</sup> A stanza after a gap.</p>
<hr/><p><small><a>PERSPECTIVES</a>mall&gt;</small></p>
<p>A stanza after a gap.</p><p><small>GENESIS 1:3</small></p>
<p>A made-up saying, on two short lines.</p><p><small>Q. Z. SOMEONE</small></p><hr/>
<p><b>MADE-UP FEATURE . . . INDEX</b></p><p><a>Patience</a></p>
<p><b>What the Bible Says about patience</b></p>
<p><b>A MADE-UP SUBHEAD</b> Second made-up verse that runs on to the end.
(Genesis 1:2)</p>
<p><b>ONE SUBHEAD</b> Fifth made-up verse . . . in a box. (Genesis 2:1)</p>
<p><b>CHARTS INDEX</b></p>
</body></html>"""


def test_epub_topics_and_boxes_are_found_and_keyed(tmp_path: Path) -> None:
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("content.opf", OPF)
        archive.writestr(
            "OEBPS/a.html", PAGE.replace("MADE-UP FEATURE", "WHAT THE BIBLE SAYS ABOUT")
        )
    _, notes = parse_notes(document(), PUBLIC)
    topics = parse_epub_topics(path, notes.features.topic_order)
    assert topics.texts[("WBSA 1", 0, 1)] == (
        "A MADE-UP SUBHEAD Second made-up verse that runs on to the end. (Genesis 1:2)"
    )
    # the second topic's head is lost: it is found by its first subhead, and damaged
    assert topics.texts[("WBSA 2", 0, 1)].startswith("ONE SUBHEAD Fifth made-up verse")
    assert topics.damaged == {("WBSA 2", 0, 1)} and not topics.missing
    boxes = parse_epub_boxes(path, notes.features.box_order)
    assert boxes.texts[("PERSP Genesis 1:3", 0, 1)] == (
        "A stanza after a gap. GENESIS 1:3 A made-up saying, on two short lines. Q. Z. SOMEONE"
    )
    assert boxes.missing == [("PERSP Genesis 1:1; 1:2", 0, 1)]  # not in this EPUB
