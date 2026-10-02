"""EMB's textual and study notes, end to end on synthetic pdftohtml XML (V8-S2b; made-up text
only): blocks and labels, pairing with the ``*`` markers, anchors, study-note references and
callouts, ``ref:`` links, the EPUB witness, and the file Concord's loader reads."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from bible_core.loader import build_database
from emb_convert.convert import translation_payload
from emb_convert.crosscheck import Verdict, cross_check_notes
from emb_convert.epub_notes import parse_epub_notes
from emb_convert.layout import canonical_books
from emb_convert.notes import notes_payload
from emb_convert.study import Part, parse_parts, passages, shape
from emb_convert.text import Marker, Where
from emb_convert.textual import LabelKind, TextualNote, match, parse_label
from pdfxmlkit import (
    NOTES_PAGE,
    STUDY_NOTES_PAGE,
    T,
    body,
    callout_number,
    header,
    heading,
    italic,
    label,
    link,
    marker,
    notes_header,
    parse_notes,
    start,
    study_head,
    title_label,
    vnum,
)

GEN = start("GEN") + 1
PSA = start("PSA") + 1
BY_ALIAS = {alias: seed.id for seed in canonical_books() for alias in seed.aliases}

# Genesis 1: a * in verse 1, two in verse 2 (an a/b split), one in a heading before verse 3
GENESIS = [
    *header("GEN", 1),
    vnum("1", 100),
    body("The made-up start.", 100, 45, width=90),
    marker(100, 136),
    vnum("2", 120),
    body("Second words", 120, 45, width=60),
    marker(120, 106),
    body(" and more", 120, 110, width=50),
    marker(120, 162),
    heading("A Made-up Heading", 145),
    marker(145, 130),
    vnum("3", 165),
    body("Third verse.", 165, 45, width=60),
]
# Psalm 4: a * on the chapter header and one in the title
PSALM = [
    *header("PSA", 4),
    marker(65, 120, NOTES_PAGE + 1),
    italic("A song", 85, 38),
    marker(85, 70, NOTES_PAGE + 1),
    vnum("1", 110, 46),
    body("Hear.", 110, 50),
]
TEXTUAL = {
    GEN: GENESIS,
    PSA: PSALM,
    NOTES_PAGE: [
        label("1:1", 97, GEN),
        T(" Or ", 97, 54),
        italic("the start;", 97, 75),
        T(" also later.", 97, 125),
        label("1:2a", 126, GEN),
        T(" Or ", 126, 64),
        italic("Second", 126, 80),
        label("1:2b", 155, GEN),
        T(" Hebrew reads ", 155, 64),
        italic("and more.", 155, 140),
        label("1:2", 184, GEN),
        T(" The heading is made up.", 184, 60),
    ],
    NOTES_PAGE + 1: [
        *notes_header("Psalm 4 Textual", "Notes"),
        label("4", 97, PSA),
        T(" A made-up chapter note.", 97, 50),
        *title_label(4, 126, PSA),
        T(" Hebrew ", 126, 70),
        italic("made-up.", 126, 110),
    ],
}


def notes_of(result: Any, kind: str) -> list[dict[str, Any]]:
    return [n for n in result.payload if n["type"] == kind]


# -- textual notes ----------------------------------------------------------------------------


def test_label_forms_and_their_kinds() -> None:
    def kind(text: str, book: str = "GEN", chapter: int = 1, title: bool = False) -> object:
        parsed = parse_label(text, book, chapter, title=title)
        return parsed if isinstance(parsed, str) else (parsed.kind, parsed.first, parsed.last)

    assert kind("1:26") == (LabelKind.VERSE, 26, 26)
    assert kind("1:26b") == (LabelKind.LETTERED, 26, 26)
    assert kind("1:12-13") == (LabelKind.RANGE, 12, 13)
    assert kind("1:11b-12") == (LabelKind.RANGE, 11, 12)
    assert kind("6:", "PSA", 6, title=True) == (LabelKind.TITLE, 1, 1)
    assert kind("25", "PSA", 25) == (LabelKind.CHAPTER, 1, 1)
    assert kind("9", "JUD") == (LabelKind.SINGLE, 9, 9)
    assert kind("22-23a", "JUD") == (LabelKind.SINGLE, 22, 23)
    assert isinstance(kind("2:1"), str)  # another chapter's label in chapter 1's block
    assert isinstance(kind("7", "GEN", 1), str)  # a bare number outside a single-chapter book


def test_blocks_and_notes_pair_with_markers_and_anchor_where_the_star_sat() -> None:
    _, notes = parse_notes(TEXTUAL)
    assert notes.textual.blocks == 2  # one header wrapped onto two lines
    assert notes.matching.ok and len(notes.matching.pairs) == 6
    anchors = [(n["book"], n["verse"], n["char_offset"]) for n in notes_of(notes, "tn")]
    assert anchors == [
        ("GEN", 1, 18),  # after "The made-up start."
        ("GEN", 2, 12),  # 1:2a, after "Second words"
        ("GEN", 2, 21),  # 1:2b, after "Second words and more"
        ("GEN", 2, 21),  # the heading's *, labelled 1:2: the end of verse 2, above the heading
        ("PSA", 1, 0),  # the chapter header's *
        ("PSA", 1, 6),  # the title's *, after "A song" (verse 1's prefix)
    ]
    assert notes.anchors == {"verse": 3, "heading": 1, "chapter header": 1, "psalm title": 1}
    assert notes.lettered == (2, 1)
    first = notes_of(notes, "tn")[0]
    assert first["label"] == "Textual Note" and first["marker"] == "*"
    assert first["text"] == "Or *the start*; also later." and first["text_format"] == "markdown"
    assert "text_format" not in notes_of(notes, "tn")[3]  # no italics: plain text


def _note(book: str, chapter: int, text: str) -> TextualNote:
    parsed = parse_label(text, book, chapter, title=False)
    assert not isinstance(parsed, str)
    return TextualNote(book, chapter, parsed, 1, [], 0)


def test_a_marker_without_a_note_and_a_note_without_a_marker_are_reported() -> None:
    markers = [
        Marker("GEN", 1, 1, 5, Where.VERSE, 1, 1),
        Marker("GEN", 1, 3, 2, Where.VERSE, 1, 2),
        Marker("GEN", 1, 4, 0, Where.VERSE, 1, 3),
    ]
    notes = [_note("GEN", 1, "1:1"), _note("GEN", 1, "1:2"), _note("GEN", 1, "1:4")]
    result = match(notes, markers, {})
    assert [(p.note.label.text, p.marker.verse) for p in result.pairs] == [("1:1", 1), ("1:4", 4)]
    assert [m.verse for m in result.markers_without_note] == [3]
    assert [n.label.text for n in result.notes_without_marker] == ["1:2"]
    assert not result.ok


def test_letters_must_ascend_within_a_verse() -> None:
    markers = [Marker("GEN", 1, 2, n, Where.VERSE, 1, n + 1) for n in range(2)]
    notes = [_note("GEN", 1, "1:2b"), _note("GEN", 1, "1:2a")]
    assert match(notes, markers, {}).letter_errors == ["GEN 1:2 letters ba"]
    assert match([_note("GEN", 1, "1:2b-3")], markers[:1], {}).ok  # a "b" alone names a half


def test_a_combined_verse_takes_the_star_of_the_number_it_absorbs() -> None:
    marker_ = Marker("NUM", 1, 20, 10, Where.VERSE, 1, 1)
    result = match([_note("NUM", 1, "1:20-21a")], [marker_], {("NUM", 1, 20): 21})
    assert result.ok and len(result.pairs) == 1


# -- study notes ------------------------------------------------------------------------------


def test_each_reference_shape_gives_its_parts() -> None:
    assert parse_parts("GEN", "1:26-27") == [Part(1, 26, 1, 27)]
    assert parse_parts("GEN", "1:1") == [Part(1, 1, 1, 1)]
    assert parse_parts("EXO", "1:22-2:8") == [Part(1, 22, 2, 8)]
    assert parse_parts("GEN", "17:9-10,24-27") == [Part(17, 9, 17, 10), Part(17, 24, 17, 27)]
    assert parse_parts("JHN", "13:23;19:26;21:20") == [
        Part(13, 23, 13, 23),
        Part(19, 26, 19, 26),
        Part(21, 20, 21, 20),
    ]
    assert parse_parts("OBA", "3-4") == [Part(1, 3, 1, 4)]
    assert isinstance(parse_parts("GEN", "1:9-3"), str)  # ends before it starts


def test_shapes_and_passages() -> None:
    _, notes = parse_notes(
        {
            GEN: GENESIS,
            STUDY_NOTES_PAGE: [
                *study_head("Gen.", "1:1-3", 60, GEN),
                T("A made-up note on the whole chapter.", 74, 38),
            ],
        }
    )
    note = notes.study.notes[0]
    assert shape(note, {("GEN", 1): 3}) == "whole chapter"
    assert shape(note, {("GEN", 1): 31}) == "range"
    assert passages(note, (1, 1)) == [Part(1, 1, 1, 3)]
    single = parse_parts("GEN", "1:2")
    assert not isinstance(single, str)
    note.parts = single
    assert passages(note, (1, 2)) == []  # the anchor is the whole note


CALLOUTS = {
    GEN: [
        *header("GEN", 1),
        callout_number("1", 100),
        body("One made-up verse.", 100, 45),
        vnum("2", 120),
        body("Two.", 120, 45),
        vnum("3", 140),
        body("Three.", 140, 45),
        *header("GEN", 2, 170),
        callout_number("1", 200),
        body("A second chapter.", 200, 45),
        vnum("2", 220),
        body("More.", 220, 45),
    ],
    STUDY_NOTES_PAGE: [
        *study_head("Gen.", "1:1", 60, GEN),
        T("A made-up note on the start.", 74, 38),
        *study_head("Gen.", "1:1-3", 100, GEN),
        T("Another note from the same verse.", 114, 38),
        *study_head("Gen.", "1:2; 2:1-2", 140, GEN),
        T("A note the book calls out at its second part.", 154, 38),
    ],
}


def test_a_study_note_anchors_where_the_book_calls_it_out() -> None:
    _, notes = parse_notes(CALLOUTS)
    study = notes_of(notes, "sn")
    assert [(n["chapter"], n["verse"], n["char_offset"]) for n in study] == [
        (1, 1, 0),
        (1, 1, 0),  # no callout of its own: its first verse
        (2, 1, 0),  # called out at 2:1, its second part
    ]
    assert study[2]["passages"] == [
        {"start_chapter": 1, "start_verse": 2, "end_chapter": 1, "end_verse": 2},
        {"start_chapter": 2, "start_verse": 1, "end_chapter": 2, "end_verse": 2},
    ]
    assert "passages" not in study[0]  # a single verse, anchored there
    assert study[1]["passages"] == [
        {"start_chapter": 1, "start_verse": 1, "end_chapter": 1, "end_verse": 3}
    ]
    assert notes.later_callouts == ["Gen. 1:2; 2:1-2 (called out at 2:1)"]
    assert study[0]["label"] == "Study Note" and "text_format" not in study[0]
    assert notes.ok


def test_a_callout_without_a_note_is_reported() -> None:
    pages = dict(CALLOUTS)
    pages[STUDY_NOTES_PAGE] = [*study_head("Gen.", "1:2", 60, GEN), T("Only this.", 74, 38)]
    _, notes = parse_notes(pages)
    assert [(c.chapter, c.verse) for c in notes.callouts.unmatched] == [(1, 1), (2, 1)]
    assert not notes.ok


# Genesis 1–2 with one study-note callout, at 1:1
ONE_CALLOUT = [
    vnum("1", 200) if item.text == "1" and item.top == 198 else item for item in CALLOUTS[GEN]
]


def test_linked_references_become_ref_links() -> None:
    _, notes = parse_notes(
        {
            GEN: ONE_CALLOUT,
            STUDY_NOTES_PAGE: [
                *study_head("Gen.", "1:1", 60, GEN),
                T("See ", 74, 38, width=20),
                link("1:2", 74, 58, GEN),
                T("; ", 74, 73),
                link("Exodus 3:1", 74, 83, GEN),  # the book links it to the wrong page
                T("; ", 74, 133),
                link("3:2", 74, 143, GEN),  # the book points it at this note's own verse
                T(", and ", 74, 158),
                link("2:1, 2", 74, 188, GEN),
                T(" and ", 74, 218),
                link("chapter 2", 74, 243, GEN),
                T(" and ", 74, 288, width=20),
                link("1:2-", 74, 308, GEN, width=25),  # a link wrapped onto the next line
                link("3", 88, 38, GEN),
                T(" end.", 88, 45),
            ],
        }
    )
    text = notes_of(notes, "sn")[0]["text"]
    assert text == (
        "See [1:2](ref:GEN.1.2); [Exodus 3:1](ref:EXO.3.1); [3:2](ref:EXO.3.2), and "
        "[2:1](ref:GEN.2.1), [2](ref:GEN.2.2) and [chapter 2](ref:GEN.2) and "
        "[1:2-3](ref:GEN.1.2-3) end."
    )
    evidence = {f.link: f.evidence for f in notes.links}
    assert evidence["1:2"] == "agrees"
    assert evidence["Exodus 3:1"] == "named"  # the text names its book; the target slips
    assert evidence["3:2"] == "own verse"
    assert notes.ok


def test_a_link_whose_target_disagrees_unexplained_is_reported() -> None:
    _, notes = parse_notes(
        {
            GEN: ONE_CALLOUT,
            STUDY_NOTES_PAGE: [
                *study_head("Gen.", "1:1", 60, GEN),
                T("See ", 74, 38, width=20),
                link("2:1", 74, 58, start("REV") + 1),  # bare, so Genesis: the book says Revelation
                T(".", 74, 73),
            ],
        }
    )
    assert [(f.link, f.targets, f.evidence) for f in notes.links] == [
        ("2:1", ["GEN.2.1"], "unexplained")
    ]
    assert not notes.ok


# -- the EPUB witness -------------------------------------------------------------------------

CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""
OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0"><manifest>
<item id="a" href="OEBPS/a.html" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="a"/></spine></package>"""
NOTES_PAGE_HTML = """<html><body>
<p>The Bible text, before the notes.</p>
<h1>Genesis 1 Textual Notes</h1>
<p><a href="x"><b>1:1</b></a> Or <i>the start;</i> also later.</p>
<p><b>1:2a</b> Or <i>Second</i></p>
<p>filepos=0000123 &gt;<b>1:2b</b> Hebrew reads <i>and more.</i> ht="0"&gt;</p>
<span>Genesis 3 Textual Notes</span><p><b>3:1</b> A third-chapter note.</p>
<p><b>1:5</b> A note whose block header the conversion dropped.</p>
<span>Psalm 4 Textual Notes</span>
<span><a><b>4:</b></a><small><b>TITLE</b></small> Hebrew <i>made-up.</i></span>
<p>MEN, WOMEN, AND GOD INDEX</p>
<p><b>A Feature Title</b> feature words.</p>
<b><span>Gen. </span><span>1:1</span></b> <span>A made-up note on the start.</span>
<b>Gen. 1:1-3</b> <span>Another note.</span>
<b>Gen. 0004 &gt;1:4</b> <span>A note under a damaged heading.</span>
</body></html>"""


def test_epub_notes_are_read_by_block_label_and_heading(tmp_path: Path) -> None:
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("content.opf", OPF)
        archive.writestr("OEBPS/a.html", NOTES_PAGE_HTML)
    notes = parse_epub_notes(path, BY_ALIAS, ("GEN", "1:1"), ["GEN", "EXO", "PSA"])
    assert notes.textual[("GEN", 1, "1:1", 1)] == "Or the start; also later."
    assert notes.textual[("GEN", 1, "1:2a", 1)] == "Or Second filepos=0000123 >"  # a scrap
    assert notes.textual[("GEN", 1, "1:2b", 1)] == 'Hebrew reads and more. ht="0">'
    assert notes.textual[("GEN", 3, "3:1", 1)] == "A third-chapter note."
    assert notes.textual[("EXO", 1, "1:5", 1)].startswith("A note whose")  # header was lost
    assert notes.textual[("PSA", 4, "4:TITLE", 1)] == "Hebrew made-up."
    assert notes.study == {
        ("GEN", "1:1", 1): "A made-up note on the start.",
        ("GEN", "1:1-3", 1): "Another note.",
        ("GEN", "1:4", 1): "A note under a damaged heading.",
    }
    assert notes.damaged == {("GEN", "1:4", "1")}  # its heading read past "0004 >"


def test_note_cross_check_classes() -> None:
    def key(n: int) -> tuple[str, int, int]:
        return ("tn GEN 1:1", 1, n)

    fixed = {
        key(1): "a good day",
        key(2): "make it",
        key(3): "a goodday",
        key(4): "the first month",
    }
    raw = {
        key(1): "a good day",
        key(2): "mak e it",
        key(3): "a good day",
        key(4): "the first month",
    }
    epub = {
        key(1): "a good day",
        key(2): "make it",
        key(3): "a good day",
        key(4): "the month",
        key(5): 'words ht="0">',
    }
    spans = {k: (10, 10) for k in fixed}
    result = cross_check_notes(
        fixed, raw, {}, epub, set(), fixed, {10: "a page of text"}, spans, frozenset({key(4)})
    )
    verdicts = {f.key[2]: f.verdict for f in result.findings}
    assert verdicts == {
        1: Verdict.AGREE,
        2: Verdict.FIXED_QUIRK,
        3: Verdict.FIX_REGRESSION,
        4: Verdict.VERIFIED,  # the PDF prints "first": checked on the rendered page
        5: Verdict.EPUB_VISIBLE,  # an EPUB-only note with scraps
    }


def test_epub_spacing_artifacts_do_not_count_as_differences() -> None:
    k = ("sn GEN 1:1", 0, 1)
    result = cross_check_notes(
        {k: "see (Acts 2:5-12). Then—now."},
        {k: "see (Acts 2:5-12). Then—now."},
        {},
        {k: "see (Acts 2: 5-12 ) . Then —now."},
        set(),
        {k: "see"},
        {10: "x"},
        {k: (10, 10)},
    )
    assert result.findings[0].verdict is Verdict.AGREE


def test_a_spacing_difference_is_judged_space_by_space() -> None:
    """The 2 Cor 12:1 shape (made-up words): the EPUB prints the same broken word, so a
    non-word sits beside the difference — it must not excuse the space the fix took out."""

    def key(n: int) -> tuple[str, int, int]:
        return ("sn GEN 1:1", 0, n)

    fixed = {
        key(1): "the glimmering(here now",  # the fix glued the bracket on
        key(2): "the glimmering (here now",  # the fix joined the broken word only
        key(3): "they bark ed up",  # a broken word the PDF kept
        key(4): "their way",  # the EPUB split a word the PDF prints whole
        key(5): "it self-giving",  # the fix joined two words both sides print
    }
    raw = {
        key(1): "the glim mering (here now",
        key(2): "the glim mering (here now",
        key(3): "they bark ed up",
        key(4): "their way",
        key(5): "it self-giving",
    }
    epub = {  # 2: damaged elsewhere too, as EPUB notes mostly are
        key(1): "the glim mering (here now",
        key(2): 'the glim mering (here now ht="0">',
        key(3): "they barked up",
        key(4): "the ir way",
        key(5): "it self-giving",
    }
    fixed[key(5)] = "itself-giving"
    spans = {k: (10, 10) for k in fixed}
    context = {**fixed, ("x", 0, 0): "the way they barked"}
    result = cross_check_notes(fixed, raw, {}, epub, set(), context, {10: "x"}, spans)
    verdicts = {f.key[2]: f.verdict for f in result.findings}
    assert verdicts == {
        1: Verdict.FIX_REGRESSION,
        2: Verdict.EPUB_VISIBLE,
        3: Verdict.OPEN,
        4: Verdict.EPUB_VISIBLE,
        5: Verdict.FIX_REGRESSION,
    }


def test_note_text_with_a_mark_out_of_place_blocks_the_write() -> None:
    pages = {**TEXTUAL, NOTES_PAGE: list(TEXTUAL[NOTES_PAGE])}
    pages[NOTES_PAGE][1] = T(" Or near(the ", 97, 54)
    _, notes = parse_notes(pages)
    assert notes.hygiene["word-into-opening-mark"]
    assert not notes.ok


# -- the file Concord loads -------------------------------------------------------------------


def test_notes_file_loads_through_concords_loader(tmp_path: Path) -> None:
    pages = dict(TEXTUAL)
    pages[STUDY_NOTES_PAGE] = [
        *study_head("Gen.", "1:1-3", 60, GEN),
        T("A made-up note on the chapter.", 74, 38),
        *study_head("Gen.", "1:2", 100, GEN),
        T("See ", 114, 38),
        link("1:3", 114, 60, GEN),
        T(".", 114, 75),
    ]
    result, notes = parse_notes(pages)
    assert notes.ok
    data, notes_dir = tmp_path / "data", tmp_path / "notes"
    data.mkdir()
    notes_dir.mkdir()
    (data / "EMB.json").write_text(json.dumps(translation_payload(result, "Rights.")), "utf-8")
    (notes_dir / "EMB.json").write_text(json.dumps(notes_payload(notes, "EMB")), "utf-8")
    build_database(tmp_path / "bible.db", [data], notes_dirs=[notes_dir])
    with sqlite3.connect(tmp_path / "bible.db") as conn:
        rows = conn.execute(
            "SELECT book_id, chapter, verse, note_type, label, text_format, char_offset "
            "FROM translator_notes ORDER BY id"
        ).fetchall()
        passages_ = conn.execute("SELECT COUNT(*) FROM note_passages").fetchone()
    assert rows == [
        ("GEN", 1, 1, "sn", "Study Note", None, 0),
        ("GEN", 1, 1, "tn", "Textual Note", "markdown", 18),
        ("GEN", 1, 2, "sn", "Study Note", "markdown", 0),  # it carries a ref: link
        ("GEN", 1, 2, "tn", "Textual Note", "markdown", 12),
        ("GEN", 1, 2, "tn", "Textual Note", "markdown", 21),
        ("GEN", 1, 2, "tn", "Textual Note", None, 21),
        ("PSA", 4, 1, "tn", "Textual Note", None, 0),
        ("PSA", 4, 1, "tn", "Textual Note", "markdown", 6),
    ]
    assert passages_ == (1,)  # 1:1-3; the single-verse note has none


def test_same_input_gives_identical_notes() -> None:
    first = json.dumps(notes_payload(parse_notes(CALLOUTS)[1], "EMB"), ensure_ascii=False)
    second = json.dumps(notes_payload(parse_notes(CALLOUTS)[1], "EMB"), ensure_ascii=False)
    assert first == second
