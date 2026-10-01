"""The EMB converter's Bible-text pass, on synthetic pdftohtml XML (made-up text)."""

from __future__ import annotations

from emb_convert.clean import Fixes
from emb_convert.layout import find_layout
from emb_convert.pdfxml import parse_pdf_xml
from emb_convert.text import Where
from pdfxmlkit import (
    FEATURES_PAGE,
    NOTES_PAGE,
    T,
    body,
    box,
    callout,
    document,
    full,
    header,
    heading,
    italic,
    marker,
    nav,
    parse,
    start,
    verse_texts,
    vnum,
)

GEN = start("GEN") + 1


def headings_of(result: object, code: str, chapter: int) -> list[tuple[int, str]]:
    for book in getattr(result, "books"):  # noqa: B009 - ParseResult from the kit
        if book.code == code:
            for ch in book.chapters:
                if ch.number == chapter:
                    return [(h.before_verse, h.text) for h in ch.headings]
    return []


# -- reader and layout ------------------------------------------------------------------


def test_reader_keeps_size_colour_style_and_link() -> None:
    doc = parse_pdf_xml(document({GEN: [T("Word", 90, 50, 12, blue=True, bold=True, link=7)]}))
    item = next(i for i in doc.items if i.text == "Word")
    assert (item.page, item.top, item.left, item.size) == (GEN, 90, 50, 12)
    assert item.blue and item.bold and not item.italic and item.link_page == 7


def test_layout_finds_books_and_link_regions() -> None:
    doc = parse_pdf_xml(document({}))
    layout = find_layout(doc)
    assert len(layout.books) == 66 and layout.books[0].code == "GEN"
    assert layout.notes_start == NOTES_PAGE
    assert layout.link_kind(NOTES_PAGE).value == "textual-note"
    assert layout.link_kind(FEATURES_PAGE + 1).value == "feature"


# -- chapters and verses ---------------------------------------------------------------


def test_verses_and_continuation_lines() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                vnum("1", 100),
                body("First words of the opening", 100, 45, width=200),
                body("verse go on here.", 115, 38),
                vnum("2", 130),
                body("A second verse.", 130, 45),
            ]
        }
    )
    texts = verse_texts(result)
    assert texts[("GEN", 1, 1)] == "First words of the opening verse go on here."
    assert texts[("GEN", 1, 2)] == "A second verse."
    assert not result.diagnostics.unclassified


def test_intro_and_navigation_list_are_never_verse_text() -> None:
    first = start("GEN")
    result = parse(
        {
            first: [*nav("GEN", 2), body("An introduction sentence.", 120, 38)],
            GEN: [*header("GEN", 1), vnum("1", 100), body("Verse text.", 100, 45)],
        }
    )
    assert verse_texts(result)[("GEN", 1, 1)] == "Verse text."
    assert result.diagnostics.nav_chapters["GEN"] == 2


def test_single_chapter_book_opens_at_its_first_verse_number() -> None:
    oba = start("OBA")
    result = parse(
        {oba: [body("Intro words.", 60, 38), vnum("1", 100), body("Vision words.", 100, 45)]}
    )
    assert verse_texts(result) == {("OBA", 1, 1): "Vision words."}


def test_chapter_label_turns_the_chapter_before_its_header() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                vnum("1", 100),
                body("One.", 100, 45),
                T("2:", 113, 38, 7),
                vnum("1", 115, 50),
                body("Two one.", 115, 60),
                *header("GEN", 2, 200),
                vnum("2", 250),
                body("Two two.", 250, 45),
            ]
        }
    )
    texts = verse_texts(result)
    assert texts[("GEN", 2, 1)] == "Two one." and texts[("GEN", 2, 2)] == "Two two."
    assert result.diagnostics.counts["chapter-headers-after-label"] == 1


def test_combined_verse_is_stored_under_its_first_number() -> None:
    result = parse({GEN: [*header("GEN", 1), vnum("1-2", 100), body("Both verses.", 100, 50)]})
    verse = result.books[0].chapters[0].verses[0]
    assert (verse.number, verse.last, verse.text) == (1, 2, "Both verses.")
    assert result.diagnostics.combined == ["GEN 1:1-2"]


# -- headings ---------------------------------------------------------------------------


def test_headings_attach_before_the_next_verse_and_wrapped_lines_join() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                heading("A Long Heading That", 90),
                heading("Wraps Here", 104),
                vnum("1", 120),
                body("One.", 120, 45),
                heading("Second Part", 150),
                vnum("2", 170),
                body("Two.", 170, 45),
            ]
        }
    )
    assert headings_of(result, "GEN", 1) == [
        (1, "A Long Heading That Wraps Here"),
        (2, "Second Part"),
    ]


def test_heading_above_a_chapter_header_belongs_to_the_new_chapter() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                vnum("1", 100),
                body("One.", 100, 45),
                heading("Next Part", 200),
                *header("GEN", 2, 230),
                vnum("1", 280),
                body("Two one.", 280, 45),
            ]
        }
    )
    assert headings_of(result, "GEN", 2) == [(1, "Next Part")]


def test_mid_verse_heading_attaches_to_the_verse_it_interrupts() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                vnum("1", 100),
                body("Opening line.", 100, 45),
                heading("Inside the Verse", 130),
                body("More of verse one.", 150, 46),
                vnum("2", 170),
                body("Two.", 170, 45),
            ]
        }
    )
    assert headings_of(result, "GEN", 1) == [(1, "Inside the Verse")]
    assert verse_texts(result)[("GEN", 1, 1)] == "Opening line. More of verse one."
    assert result.diagnostics.mid_verse_headings == ["GEN 1:1"]


def test_small_caps_join_in_text_and_headings() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                T("Song of the L", 90, 38, bold=True, italic=True, width=80),
                T("ORD", 93, 118, 7, bold=True, italic=True),
                vnum("1", 120),
                body("Then the L", 120, 45, width=60),
                T("ORD", 123, 105, 7),
                body(" spoke.", 120, 125),
            ]
        }
    )
    assert headings_of(result, "GEN", 1) == [(1, "Song of the LORD")]
    assert verse_texts(result)[("GEN", 1, 1)] == "Then the LORD spoke."


# -- italic-only lines -------------------------------------------------------------------


def test_psalm_title_prefixes_verse_one_and_interlude_stays_in_the_verse() -> None:
    psa = start("PSA") + 1
    result = parse(
        {
            psa: [
                *header("PSA", 3),
                italic("A song of someone, when he ran.", 85),
                vnum("1", 110, 46),
                body("O God, hear me.", 110, 50),
                italic("Interlude", 125, 280),
                vnum("2", 140, 46),
                body("Answer me.", 140, 50),
            ]
        }
    )
    texts = verse_texts(result)
    assert texts[("PSA", 3, 1)] == "A song of someone, when he ran. O God, hear me. Interlude"
    assert result.diagnostics.counts["italic:psalm-title"] == 1
    assert result.diagnostics.counts["italic:psalm-verse-text"] == 1


def test_stanza_and_speaker_labels_become_headings() -> None:
    psa, sng = start("PSA") + 2, start("SNG") + 1
    result = parse(
        {
            psa: [
                *header("PSA", 119),
                italic("Alpha", 85),
                vnum("1", 100, 46),
                body("Line.", 100, 50),
            ],
            sng: [
                *header("SNG", 1),
                vnum("1", 90, 46),
                body("A title verse.", 90, 50),
                italic("Speaker One", 110),
                vnum("2", 130, 46),
                body("Words of one.", 130, 50),
                italic("Speaker Two", 150),
                body("Words of two, same verse.", 170, 46),
            ],
        }
    )
    assert headings_of(result, "PSA", 119) == [(1, "Alpha")]
    assert headings_of(result, "SNG", 1) == [(2, "Speaker One"), (2, "Speaker Two")]
    assert verse_texts(result)[("SNG", 1, 2)] == "Words of one. Words of two, same verse."
    assert result.diagnostics.mid_verse_headings == ["SNG 1:2"]


def test_italic_line_finishing_a_sentence_is_verse_text_but_a_stray_one_is_not() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                vnum("1", 100),
                body("It is written in the", 100, 45),
                italic("Scroll of Things.", 115),
                vnum("2", 140),
                body("A complete sentence.", 140, 45),
                italic("A stray italic line", 160),
            ]
        }
    )
    assert verse_texts(result)[("GEN", 1, 1)] == "It is written in the Scroll of Things."
    assert result.diagnostics.counts["italic:sentence-continuation"] == 1
    assert any("italic-only" in u for u in result.diagnostics.unclassified)


# -- markers ----------------------------------------------------------------------------


def test_markers_are_removed_with_their_offsets() -> None:
    psa = start("PSA") + 1
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                vnum("1", 100),
                body("The first words.", 100, 45, width=80),
                marker(100, 126),
                body(" More words.", 100, 132),
            ],
            psa: [
                *header("PSA", 4),
                marker(65, 120),
                italic("A song", 85, 38),
                marker(85, 70),
                vnum("1", 110, 46),
                body("Hear.", 110, 50),
            ],
        }
    )
    texts = verse_texts(result)
    assert texts[("GEN", 1, 1)] == "The first words. More words."
    gen = [m for m in result.markers if m.book == "GEN"]
    assert [(m.verse, m.offset, m.where) for m in gen] == [(1, 16, Where.VERSE)]
    assert texts[("PSA", 4, 1)] == "A song Hear."
    psa_marks = sorted((m.where.value, m.offset) for m in result.markers if m.book == "PSA")
    assert psa_marks == [("chapter", 0), ("title", 6)]


# -- things that are never verse text ------------------------------------------------------


def test_perspectives_box_is_set_aside_even_mid_verse() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                vnum("1", 100),
                body("Verse starts", 100, 45),
                *box(130, GEN),
                body("and verse ends.", 240, 38),
                vnum("2", 260),
                body("Two.", 260, 45),
            ]
        }
    )
    assert verse_texts(result)[("GEN", 1, 1)] == "Verse starts and verse ends."
    assert result.diagnostics.counts["perspectives-boxes"] == 1
    assert not result.diagnostics.errors


def test_callout_label_is_set_aside_even_mid_verse() -> None:
    result = parse(
        {
            GEN: [
                *header("GEN", 1),
                vnum("1", 100),
                body("Verse starts", 100, 45),
                callout("A Feature Title", 120),
                body("and verse ends.", 140, 38),
            ]
        }
    )
    assert verse_texts(result)[("GEN", 1, 1)] == "Verse starts and verse ends."
    assert result.diagnostics.callout_labels == [("GEN", 1, "A Feature Title")]


# -- quirk fixes ---------------------------------------------------------------------------


def test_fractions_join_as_vulgar_fractions_but_stay_raw_without_fixes() -> None:
    pages = {
        GEN: [
            *header("GEN", 1),
            vnum("1", 100),
            body("A wall 7", 100, 45, width=40),
            T("1", 99, 86, 7),
            T("/", 99, 90, 7),
            T("2", 99, 93, 7),
            body(" cubits high.", 100, 98),
        ]
    }
    assert verse_texts(parse(pages))[("GEN", 1, 1)] == "A wall 7½ cubits high."
    assert verse_texts(parse(pages, Fixes.none()))[("GEN", 1, 1)] == "A wall 71/2 cubits high."


def test_broken_word_at_a_justified_line_start_joins() -> None:
    pages = {
        GEN: [
            *header("GEN", 1),
            vnum("1", 100),
            full("It was very", 100, 45),
            T("g o o d . ", 115, 38, width=34),
            vnum("2", 115, 72),
            T("Then  more  words  followed  here.", 115, 80, width=261),
        ]
    }
    fixed = parse(pages, public=("it was good",))
    assert verse_texts(fixed)[("GEN", 1, 1)] == "It was very good."
    raw = parse(pages, Fixes.none(), public=("it was good",))
    assert verse_texts(raw)[("GEN", 1, 1)] == "It was very g o o d ."


def test_ordinary_words_at_a_line_start_are_left_alone() -> None:
    pages = {
        GEN: [
            *header("GEN", 1),
            vnum("1", 100),
            full("Then he said that", 100, 45),
            T("I am a ", 115, 38, width=30),
            vnum("2", 115, 70),
            T("Next  words  of  verse  two.", 115, 78, width=263),
        ]
    }
    assert verse_texts(parse(pages))[("GEN", 1, 1)] == "Then he said that I am a"


def test_hyphen_joins_only_a_wrapped_line_and_em_dash_keeps_a_poetic_break() -> None:
    pages = {
        GEN: [
            *header("GEN", 1),
            vnum("1", 100),
            full("plants bearing seed-", 100, 45),
            body("bearing fruit.", 115, 38),
            vnum("2", 140, 46),
            T("He spoke forever—", 140, 50, width=290),
            body("the next poetic line.", 155, 46),
        ]
    }
    texts = verse_texts(parse(pages))
    assert texts[("GEN", 1, 1)] == "plants bearing seed-bearing fruit."
    assert texts[("GEN", 1, 2)] == "He spoke forever— the next poetic line."
    assert verse_texts(parse(pages, Fixes.none()))[("GEN", 1, 1)] == (
        "plants bearing seed- bearing fruit."
    )


def test_fused_compound_gets_its_hyphen_back_from_the_pdfs_own_evidence() -> None:
    pages = {
        GEN: [
            *header("GEN", 1),
            vnum("1", 100),
            body("His son-in-law came; the father waited.", 100, 45),
            vnum("2", 120),
            body("Then her fatherin-law left.", 120, 45),
        ]
    }
    assert verse_texts(parse(pages))[("GEN", 1, 2)] == "Then her father-in-law left."
    assert verse_texts(parse(pages, Fixes.none()))[("GEN", 1, 2)] == ("Then her fatherin-law left.")
