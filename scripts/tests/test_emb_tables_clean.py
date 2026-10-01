"""Tables and the quirk-fix units of the EMB converter (made-up text)."""

from __future__ import annotations

from emb_convert.clean import (
    CompoundRepair,
    Fixes,
    PublicWords,
    Vocabulary,
    fraction,
    letter_spacing,
)
from pdfxmlkit import T, body, header, parse, start, verse_texts, vnum

NUM = start("NUM") + 1


def census(split_page: bool) -> dict[int, list[T]]:
    """Num 1-style table: a header row, rows with verse numbers, a row split by a page."""
    first = [
        *header("NUM", 1),
        vnum("5", 100),
        body("These are the names:", 100, 45),
        T("Tribe", 200, 40, bold=True, italic=True),
        T("Leader", 200, 188, bold=True, italic=True),
        T("Ruben", 220, 40),
        T("  Alder son of Bent", 220, 181),
        vnum("6", 240, 40),
        T("Simon", 240, 44),
        T("  Shel son of Zur", 240, 181),
    ]
    rest = [
        vnum("7", 40, 40),
        T("Judah", 40, 44),
        vnum("8", 58, 40),
        T("Ishar", 58, 44),
        T("  Neth son of Zu", 58, 181),
        vnum("9", 100, 38),
        body("So it was done.", 100, 45),
    ]
    if split_page:
        first.append(T("  Nash son of Amm", 460, 181))
        return {NUM: first, NUM + 1: rest}
    rest.insert(2, T("  Nash son of Amm", 40, 181))
    return {NUM: first + rest}


def test_table_rows_join_cells_and_drop_the_header_row() -> None:
    texts = verse_texts(parse(census(split_page=False)))
    assert texts[("NUM", 1, 5)] == "These are the names: Ruben - Alder son of Bent"
    assert texts[("NUM", 1, 6)] == "Simon - Shel son of Zur"
    assert texts[("NUM", 1, 7)] == "Judah - Nash son of Amm"
    assert texts[("NUM", 1, 9)] == "So it was done."


def test_a_cell_stranded_by_a_page_break_moves_to_its_row() -> None:
    result = parse(census(split_page=True))
    texts = verse_texts(result)
    assert texts[("NUM", 1, 6)] == "Simon - Shel son of Zur"
    assert texts[("NUM", 1, 7)] == "Judah - Nash son of Amm"
    assert result.diagnostics.tables[0].split_cells_moved == 1
    raw = verse_texts(parse(census(split_page=True), Fixes.none()))
    assert raw[("NUM", 1, 6)] == "Simon - Shel son of Zur Nash son of Amm"


def test_two_rows_in_one_verse_and_a_lone_wide_line_is_not_a_table() -> None:
    rev = start("REV") + 1
    result = parse(
        {
            rev: [
                *header("REV", 7),
                vnum("5", 100, 40),
                T("from Alpha", 100, 44),
                T("  1,000", 100, 136),
                T("from Beta", 118, 40),
                T("  2,000", 118, 136),
                vnum("6", 160, 38),
                T("Poetry", 160, 45),
                T("far apart", 160, 200),
            ]
        }
    )
    texts = verse_texts(result)
    assert texts[("REV", 7, 5)] == "from Alpha - 1,000 from Beta - 2,000"
    assert len(result.diagnostics.tables) == 1


# -- units -------------------------------------------------------------------------------


def vocab(*pdf: str) -> Vocabulary:
    return Vocabulary(PublicWords(("good things were said and asked",)), pdf)


def test_letter_spacing_joins_broken_words_only() -> None:
    v = vocab("they asked him", "it was good")
    assert letter_spacing("g o o d . ", v, whole_item=False) == "good. "
    assert letter_spacing("as ked, “Why  not", v, whole_item=False) == "asked, “Why  not"
    assert letter_spacing("for him. ", v, whole_item=False) is None
    assert letter_spacing("I am a man", v, whole_item=False) is None
    assert letter_spacing("thighs .", v, whole_item=False) == "thighs."
    assert letter_spacing("by . . . ,", v, whole_item=False) is None  # a real ellipsis


def test_letter_spacing_mid_item_only_in_italic_text() -> None:
    v = vocab("they asked him")
    text = "A song of him, as king for help"
    assert letter_spacing("A song as king for help", v, whole_item=False) is None
    assert letter_spacing("A song as ked for help", v, whole_item=True) == "A song asked for help"
    assert letter_spacing(text, v, whole_item=True) is None


def test_letter_spacing_keeps_a_small_caps_tail() -> None:
    v = vocab("the town of bethel")
    assert letter_spacing("be the L", v, whole_item=False, glued_tail=True) is None


def test_fraction_glyphs() -> None:
    assert fraction("1", "2", fixed=True) == "½"
    assert fraction("3", "4", fixed=True) == "¾"
    assert fraction("1", "2", fixed=False) == "1/2"
    assert fraction("5", "9", fixed=True) == "5⁄9"


def test_compound_repair_needs_the_pdfs_own_evidence() -> None:
    repair = CompoundRepair(["the son-in-law came", "the father spoke", "a well-known man"])
    assert repair.repair("her fatherin-law and the well-known son") == (
        "her father-in-law and the well-known son",
        1,
    )
    assert CompoundRepair(["no evidence here"]).repair("fatherin-law") == ("fatherin-law", 0)
