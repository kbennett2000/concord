"""Note text: assembly, Markdown and its two checks, and the broken-word fixes notes need
(V8-S2b; made-up text only)."""

from __future__ import annotations

from collections import Counter

from emb_convert.clean import Fixes, PublicWords, Vocabulary, letter_spacing
from emb_convert.lines import group_lines
from emb_convert.notetext import (
    NoteText,
    Piece,
    assemble,
    emphasis_ok,
    plain_of,
    relink,
    render,
)
from emb_convert.pdfxml import TextItem


def item(
    text: str,
    left: int,
    top: int = 100,
    *,
    size: int = 12,
    italic: bool = False,
    width: int | None = None,
) -> TextItem:
    return TextItem(
        page=1,
        top=top,
        left=left,
        width=width if width is not None else len(text) * 5,
        size=size,
        blue=False,
        bold=False,
        italic=italic,
        text=text,
        link_page=None,
    )


def vocabulary(*texts: str) -> Vocabulary:
    return Vocabulary(PublicWords(texts), texts)


def note(items: list[TextItem], *texts: str, fixes: Fixes | None = None) -> NoteText:
    pieces = assemble(group_lines(items), vocabulary(*texts), fixes or Fixes(), Counter())
    return render(pieces)


def checked(text: NoteText) -> str:
    """The Markdown, after both checks every Markdown note must pass."""
    assert text.markdown is not None
    assert emphasis_ok(text.markdown)
    assert plain_of(text.markdown) == text.plain
    return text.markdown


# -- Markdown ---------------------------------------------------------------------------------


def test_italic_runs_become_emphasis_with_their_edge_punctuation_outside() -> None:
    text = note(
        [
            item(" Or ", 50),
            item("the made-up word,", 70, italic=True),
            item(" and ", 160),
            item("“a quoted line.”", 185, italic=True),
        ]
    )
    assert text.plain == "Or the made-up word, and “a quoted line.”"
    assert checked(text) == "Or *the made-up word*, and “*a quoted line*.”"


def test_a_note_without_italics_stays_plain_and_unescaped() -> None:
    text = note([item(" Hebrew reads 3 units [1.4 meters].", 50)])
    assert text.markdown is None
    assert text.plain == "Hebrew reads 3 units [1.4 meters]."


def test_the_books_own_markdown_specials_are_escaped() -> None:
    text = note([item("Greek reads ", 38), item("two", 100, italic=True), item(" [3 units].", 120)])
    assert checked(text) == "Greek reads *two* \\[3 units\\]."
    assert render([Piece("1. Begun "), Piece("here", italic=True)]).markdown == "1\\. Begun *here*"


def test_emphasis_check_follows_commonmark_flanking() -> None:
    assert emphasis_ok("a *b* c") and emphasis_ok("(*b*).") and emphasis_ok("word*s* end")
    assert not emphasis_ok("a * b* c")  # an opener followed by a space
    assert not emphasis_ok("a*.b*")  # an opener before punctuation, after a letter
    assert not emphasis_ok("a *b")  # unpaired
    assert emphasis_ok("a \\*b")  # escaped: not a delimiter


def test_plain_of_undoes_escapes_and_drops_link_syntax() -> None:
    assert plain_of("see [5:9](ref:GEN.5.9) and \\[x\\] *y*") == "see 5:9 and [x] y"


def test_a_link_splits_into_one_ref_link_per_reference() -> None:
    pieces = [Piece("see "), Piece("5:9, 12", run=0), Piece(".")]
    relinked, targets = relink(pieces, {0: [(0, 3, "GEN.5.9"), (5, 7, "GEN.5.12")]})
    text = render(relinked, targets)
    assert text.plain == "see 5:9, 12."
    assert checked(text) == "see [5:9](ref:GEN.5.9), [12](ref:GEN.5.12)."


# -- assembly ---------------------------------------------------------------------------------


def test_wrapped_lines_close_up_a_hyphen_and_a_reference_dash() -> None:
    items = [
        item("Words of a fellow-", 38, 100, width=303),
        item("worker in 4:14–", 38, 114, width=303),
        item("5:2 end.", 38, 128),
    ]
    assert note(items).plain == "Words of a fellow-worker in 4:14–5:2 end."
    raw = note(items, fixes=Fixes.none()).plain
    assert raw == "Words of a fellow- worker in 4:14– 5:2 end."


def test_small_caps_glue_and_a_quoted_verse_number_stays_its_own_word() -> None:
    text = note(
        [
            item("Hebrew reads ", 38),
            item("the L", 105, italic=True),
            item("ORD", 128, 103, size=7, italic=True),
            item(" spoke.", 148, italic=True),
            item("12", 185, 99, size=7),
            item("Then more.", 195, italic=True),
        ]
    )
    assert text.plain == "Hebrew reads the LORD spoke. 12 Then more."
    assert checked(text) == "Hebrew reads *the LORD spoke*. 12 *Then more*."


def test_a_fraction_joins_as_in_the_verse_text() -> None:
    items = [
        item("A length of 7", 38),
        item("1", 103, 98, size=7),
        item("/", 107, 98, size=7),
        item("2", 110, 98, size=7),
        item(" units.", 115),
    ]
    assert note(items).plain == "A length of 7½ units."


def test_italic_font_breaks_after_k_are_joined() -> None:
    items = [item("Or ", 38), item("mak e it k now the Greek s.", 55, italic=True)]
    text = note(items, "make it known", "they know", "the Greeks came")
    assert text.plain == "Or make it know the Greeks."


def test_a_justified_note_line_joins_broken_words_anywhere_but_not_after_an_apostrophe() -> None:
    line = item("They spoke con cerning the Maker’ s plan and more words here.", 38, width=303)
    text = note([line, item("End.", 38, 114)], "concerning the plan", "the Maker’s hand")
    assert text.plain == "They spoke concerning the Maker’ s plan and more words here. End."


# -- the broken-word joiner, extended for notes ---------------------------------------------


def test_an_opening_bracket_glues_to_the_broken_word_it_opens() -> None:
    words = vocabulary("see the river")
    assert letter_spacing("( s e e the river", words, whole_item=False) == "(see the river"
    assert letter_spacing("( the river", words, whole_item=False) is None


def test_a_hyphenated_name_joins_by_its_parts() -> None:
    words = vocabulary("they camped at Ben-kazar")
    assert letter_spacing("at Ben-kaz ar.", words, whole_item=True) == "at Ben-kazar."
