"""EMB's front matter, reading plan and Personal Gold authors on synthetic pdftohtml XML (V8-S5c;
made-up text only): where each stands in the front, every reader's blocks and their Markdown,
the plan's links (a book change, a part-verse letter), the author notes and credits tied to their
articles, the checks that block the write, the loader's acceptance, and the EPUB witness."""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bible_core.documents import parse_documents_file
from bible_core.seed import load_canonical_books_text, parse_canonical_books
from emb_convert.articles import parse_articles
from emb_convert.clean import Fixes, PublicWords, Vocabulary
from emb_convert.crosscheck import Verdict
from emb_convert.documents import (
    Front,
    Witnessed,
    cross_check,
    epub_cut,
    find_front,
    italic_k,
)
from emb_convert.epub import BREAK
from emb_convert.frontmatter import FrontFindings, build_front
from emb_convert.layout import Layout, find_layout
from emb_convert.notes import Context, context
from emb_convert.notetext import Piece
from emb_convert.pdfxml import PdfDocument, parse_pdf_xml
from emb_convert.pgauthors import AuthorFindings, build_authors
from emb_convert.readingplan import PlanFindings, build_plan
from emb_convert.skeleton import load_skeleton
from emb_convert.text import ParseResult, parse_bible
from pdfxmlkit import PG_AUTHORS_PAGE, PG_PAGE, T, body, document, header, start, verse_texts, vnum

GEN = start("GEN") + 1
EXO = start("EXO") + 1
COPY, CONTENTS, PREFACE, HELPERS, NOTE, TEAM, FINDER, PLAN = 4, 6, 10, 12, 14, 16, 18, 20
OUTLINE = [
    (PREFACE, "A Made-up Preface"),
    (HELPERS, "Made-up Helpers"),
    (NOTE, "A Note on the Made-up Text"),
    (TEAM, "The Made-up Team"),
    (FINDER, "A Made-up Finder"),
    (PLAN, "A Made-up Reading Plan"),
]
PG_ARTICLE = PG_PAGE + 1

Pages = dict[int, list[T]]


def wide(text: str, top: int, left: int = 38, **style: Any) -> T:
    """A line that runs to the right margin (justified)."""
    return T(text, top, left, width=340 - left, **style)


def short(text: str, top: int, left: int = 38, **style: Any) -> T:
    return T(text, top, left, width=8 * len(text) // 2, **style)


def verses(code: str, chapter: int, count: int) -> list[T]:
    """A chapter's page: its header and ``count`` made-up verses."""
    items = header(code, chapter)
    for n in range(1, count + 1):
        items += [vnum(str(n), 80 + 20 * n), body(f"Verse {n}.", 80 + 20 * n, 45)]
    return items


BIBLE: Pages = {GEN: verses("GEN", 1, 5), GEN + 1: verses("GEN", 2, 3), EXO: verses("EXO", 1, 2)}

FRONT: Pages = {
    COPY: [
        short("Made-up words for the reader.", 54, 38, size=9),
        T("A made-up book copyright © 2000 by Nobody, its words run to the", 79, 38, 9, width=302),
        short("margin. All rights reserved.", 90, 38, size=9),
        short("ISBN 000 One", 115, 38, size=9),
        short("ISBN 001 Two", 126, 38, size=9),
    ],
    COPY + 1: [short("A new paragraph on a new page.", 40, 38, size=9)],
    CONTENTS: [
        T("CONTENTS", 54, 149, 15, bold=True),
        T("A Made-up Preface", 72, 96, italic=True, blue=True, link=PREFACE),
        short("A Part", 90, 150, italic=True),
        T("A Made-up Reading Plan", 104, 96, italic=True, blue=True, link=PLAN),
    ],
    PREFACE: [
        T("A MADE-UP", 54, 100, 15, bold=True),
        T("PREFACE", 72, 150, 15, bold=True),
        wide("Made-up words open the preface and run to the right", 90),
        short("margin of the page.", 104),
        short("A second paragraph opens at the indent, ends short.", 119, 46),
        short("A Made-up Head", 148, bold=True),
        wide("Words under the head run on to the margin", 162),
        short("and end.", 176),
    ],
    PREFACE + 1: [
        short("A paragraph opens a page at the margin.", 40),
        short("The Makers", 70, 268, italic=True),
    ],
    HELPERS: [
        T("MADE-UP HELPERS", 54, 129, 15, bold=True),
        short("Chief Maker", 86, 148, italic=True),
        short("Pat Doe", 101, 144),
        short("A Long Role That", 130, 120, italic=True),
        short("Wraps", 144, 160, italic=True),
        short("Lee Roe", 159, 150),
        short("Kim Poe", 173, 150),
    ],
    NOTE: [
        T("A NOTE ON THE", 54, 107, 15),
        T("MADE-UP TEXT", 72, 94, 15),
        short("A Bold Italic Head", 105, bold=True, italic=True),
        T("Made-up words cite ", 120, 38, width=100),
        T("Genesis 1:2", 120, 140, blue=True, link=GEN, width=60),
        T(" and run on to the margin;", 120, 200, width=140),
        short("see also ", 134),
        T("Exodus 1:1", 134, 90, blue=True, link=EXO, width=55),
        T(".", 134, 145, width=4),
        wide("•  A first item that runs to the right margin of", 163),
        short("the page and on.", 177, 55),
        short("•  A second item ends short.", 192),
        wide("Its own paragraph opens deep and runs to the", 206, 69),
        short("margin and ends.", 220, 61),
        short("Another Head", 250, bold=True),
        short("A last paragraph.", 265),
        short("THE MAKERS, Some Month 2000", 300, 143, italic=True),
    ],
    TEAM: [
        T("MADE-UP TEAM", 54, 94, 15),
        T("Some Made-up Book", 72, 81, 15, italic=True),
        short("FIRST DIVISION", 105, bold=True),
        short("Pat Doe, Senior Maker", 133),
        short("Some College", 148, italic=True),
        short("GROUP ONE", 176, italic=True),
        T("Lee Roe, ", 191, 38, width=52),
        short("Some University", 191, 90, italic=True),
        T("Kim Poe, ", 205, 38, width=52),
        T("A Long Made-up Institute of Many Words and", 205, 90, italic=True, width=250),
        short("More", 220, 55, italic=True),
    ],
    FINDER: [
        T("A MADE-UP FINDER", 54, 72, 15, bold=True),
        short("Topic", 72, blue=True, link=FINDER + 1),
        short("Topic two", 86, blue=True, link=FINDER + 1),
        short("Not a link", 101),
    ],
    PLAN: [
        T("A MADE-UP READING PLAN", 54, 92, 15, bold=True),
        short("Firstmonth", 72, blue=True, link=PLAN),
        short("Secondmonth", 86, blue=True, link=PLAN),
        short("FIRSTMONTH 1", 115, 55, bold=True, blue=True, link=PLAN),
        short("Genesis 1:1-2", 129, 46, blue=True, link=GEN),
        short("Genesis 1:3–2:1", 143, 46, blue=True, link=GEN),
        short("Genesis 2:2—Exodus 1:1", 158, 46, blue=True, link=GEN + 1),
        short("Exodus 1:2a", 172, 46, blue=True, link=EXO),
        short("Firstmonth 2", 201, 38, bold=True, blue=True, link=PLAN),
        short("Genesis 1:4", 215, 46, blue=True, link=GEN),
        short("Genesis 1:5", 229, 46, blue=True, link=GEN),
        short("Genesis 2:3", 244, 46, blue=True, link=GEN + 1),
        short("Exodus 1:1-2", 258, 46, blue=True, link=EXO),
    ],
}


def article(page: int, author: str, title: str) -> list[T]:
    """A Personal Gold article as S3a reads it."""
    return [
        T("Personal Gold", 60, 117, 23, blue=True, bold=True, link=PG_PAGE),
        T("from", 85, 86, 15, bold=True, italic=True),
        T(author, 85, 117, 15, blue=True, bold=True, link=PG_AUTHORS_PAGE),
        T("Genesis 1:1", 105, 150, blue=True, link=GEN),
        T(title, 130, 38, 15, bold=True),
        short("The text of the made-up article.", 175),
    ]


PG: Pages = {
    PG_AUTHORS_PAGE: [
        T("PERSONAL GOLD", 54, 141, bold=True),
        short("A MADE-UP SUBTITLE", 68, 97, size=9),
        T("Some Author", 96, 38, 9, blue=True, bold=True, link=PG_ARTICLE, width=60),
        T(" wrote made-up books and runs to the margin", 96, 100, width=240),
        short("of the page.", 108),
    ],
    PG_PAGE: [
        T("PERSONAL GOLD INDEX", 54, 99, 15, bold=True),
        short("A Caps Title", 87, size=9, blue=True, bold=True, link=PG_ARTICLE),
        short("Some Author", 97, 61),
        T("Some Author, ", 123, 61, width=79),
        short("A Made-up Book", 123, 140, italic=True),
        short(" (Press, 1999), p. 1.", 123, 230),
        short("Another Title", 152, size=9, blue=True, bold=True, link=PG_ARTICLE + 1),
        short("Other Writer", 162, 61),
        short("Taken from a made-up source. www.example.com.", 188, 61),
    ],
    PG_ARTICLE: article(PG_ARTICLE, "SOME AUTHOR", "A CAPS TITLE"),
    PG_ARTICLE + 1: article(PG_ARTICLE + 1, "OTHER WRITER", "ANOTHER TITLE"),
}


@dataclasses.dataclass
class Run:
    doc: PdfDocument
    layout: Layout
    result: ParseResult
    ctx: Context
    front: Front


def run(pages: Mapping[int, Sequence[T]] | None = None) -> Run:
    given = {**BIBLE, **FRONT, **PG} if pages is None else dict(pages)
    doc = parse_pdf_xml(document(given, OUTLINE))
    layout = find_layout(doc)
    words = PublicWords(())
    result = parse_bible(doc, layout, Fixes(), words)
    ctx = context(doc, layout, result, words, load_skeleton())
    return Run(doc, layout, result, ctx, find_front(doc, layout))


def front_matter(r: Run) -> FrontFindings:
    return build_front(r.front, r.layout, r.ctx)


def plan(r: Run) -> PlanFindings:
    assert r.front.plan is not None
    return build_plan(r.front.plan, r.ctx)


def authors(r: Run) -> AuthorFindings:
    region = parse_articles(r.doc, r.layout, r.ctx.by_alias, r.ctx.last_verse)
    return build_authors(r.doc, r.layout, region, r.ctx)


def text_of(found: FrontFindings, number: int) -> str:
    document_ = found.pieces[number - 1].document
    assert document_ is not None
    return str(document_["text"])


# --- where -------------------------------------------------------------------------------------


def test_the_front_is_read_by_its_links() -> None:
    r = run()
    front = r.front
    assert not front.errors
    assert front.contents == [CONTENTS]
    assert {line.page for line in front.copyright} == {COPY, COPY + 1}
    assert [s.start for s in front.pieces] == [PREFACE, HELPERS, NOTE, TEAM]
    assert [s.start for s in front.references] == [FINDER]
    assert front.plan is not None and front.plan.start == PLAN


# --- the front matter --------------------------------------------------------------------------


def test_five_pieces_by_kind_and_number() -> None:
    found = front_matter(run())
    assert found.ok, (found.errors, found.hygiene)
    assert [(d["slug"], d["kind"], d["ordinal"], d["title"]) for d in found.documents] == [
        ("front-matter-1", "front-matter", 1, "Copyright"),
        ("front-matter-2", "front-matter", 2, "A Made-up Preface"),
        ("front-matter-3", "front-matter", 3, "Made-up Helpers"),
        ("front-matter-4", "front-matter", 4, "A Note on the Made-up Text"),
        ("front-matter-5", "front-matter", 5, "The Made-up Team"),
    ]
    assert [p.reader for p in found.pieces] == ["copyright", "prose", "roles", "prose", "people"]
    assert (found.contents, found.references) == (1, 1)


def test_the_copyright_page_paragraphs_and_its_one_per_line_list() -> None:
    assert text_of(front_matter(run()), 1) == (
        "Made-up words for the reader.\n\n"
        "A made-up book copyright © 2000 by Nobody, its words run to the margin. All rights"
        " reserved.\n\n"
        "- ISBN 000 One\n"
        "- ISBN 001 Two\n\n"
        "A new paragraph on a new page."
    )


def test_prose_heads_paragraphs_and_the_signature() -> None:
    assert text_of(front_matter(run()), 2) == (
        "Made-up words open the preface and run to the right margin of the page.\n\n"
        "A second paragraph opens at the indent, ends short.\n\n"
        "## A Made-up Head\n\n"
        "Words under the head run on to the margin and end.\n\n"
        "A paragraph opens a page at the margin.\n\n"
        "*The Makers*"
    )


def test_roles_over_their_names() -> None:
    assert text_of(front_matter(run()), 3) == (
        "*Chief Maker*\\\nPat Doe\n\n*A Long Role That Wraps*\\\nLee Roe\\\nKim Poe"
    )


def test_bulleted_items_their_own_paragraphs_and_links() -> None:
    found = front_matter(run())
    assert text_of(found, 4) == (
        "## A Bold Italic Head\n\n"
        "Made-up words cite [Genesis 1:2](ref:GEN.1.2) and run on to the margin; see also"
        " [Exodus 1:1](ref:EXO.1.1).\n\n"
        "- A first item that runs to the right margin of the page and on.\n"
        "- A second item ends short.\n\n"
        "  Its own paragraph opens deep and runs to the margin and ends.\n\n"
        "## Another Head\n\n"
        "A last paragraph.\n\n"
        "*THE MAKERS, Some Month 2000*"
    )
    assert [(f.link, f.targets, f.evidence) for f in found.links] == [
        ("Genesis 1:2", ["GEN.1.2"], "agrees"),
        ("Exodus 1:1", ["EXO.1.1"], "agrees"),
    ]
    assert found.pieces[3].structures["item paragraphs"] == 1 and found.bullets == 2


def test_a_team_list_divisions_groups_and_a_wrapped_line() -> None:
    found = front_matter(run())
    assert text_of(found, 5) == (
        "*Some Made-up Book*\n\n"
        "## FIRST DIVISION\n\n"
        "Pat Doe, Senior Maker\\\n*Some College*\n\n"
        "*GROUP ONE*\n\n"
        "- Lee Roe, *Some University*\n"
        "- Kim Poe, *A Long Made-up Institute of Many Words and More*"
    )
    assert found.pieces[4].structures["people wrapped"] == 1


def test_an_unexplained_line_blocks() -> None:
    pages = {**BIBLE, **FRONT, **PG}
    pages[NOTE] = [*pages[NOTE], short("A line far off to the side.", 330, 90)]
    found = front_matter(run(pages))
    assert not found.ok
    assert any("the layout doesn't explain" in e for e in found.errors)


def test_a_printed_title_that_isnt_the_outline_name_blocks() -> None:
    pages = {**BIBLE, **FRONT, **PG}
    pages[HELPERS] = [T("SOMETHING ELSE", 54, 129, 15, bold=True), *pages[HELPERS][1:]]
    found = front_matter(run(pages))
    assert any("printed title isn't its outline name" in e for e in found.errors)


def test_the_italic_k_break_on_a_short_line() -> None:
    """A word the italic font broke right after a "k" on a line that isn't justified: a
    no-word head with a single-letter rest, or a no-word rest, joins; two words stay."""
    vocabulary = Vocabulary(PublicWords(("the book of a " * Vocabulary.COMMON_IN_PUBLIC,)), [])
    tally: Counter[str] = Counter()
    pieces = [Piece("Zorbak a, Fork elsom, the book of", italic=True), Piece("Zorbak a")]
    fixed = italic_k(pieces, vocabulary, Fixes(), tally)
    assert [p.text for p in fixed] == ["Zorbaka, Forkelsom, the book of", "Zorbak a"]
    assert tally["italic k breaks"] == 2
    assert italic_k(pieces, vocabulary, Fixes.none(), tally) == pieces


# --- the reading plan --------------------------------------------------------------------------


EXPECTED_PLAN = (
    "## FIRSTMONTH 1\n\n"
    "- [Genesis 1:1-2](ref:GEN.1.1-2)\n"
    "- [Genesis 1:3–2:1](ref:GEN.1.3-2.1)\n"
    "- [Genesis 2:2](ref:GEN.2.2-3)—[Exodus 1:1](ref:EXO.1.1)\n"
    "- [Exodus 1:2a](ref:EXO.1.2)\n\n"
    "## Firstmonth 2\n\n"
    "- [Genesis 1:4](ref:GEN.1.4)\n"
    "- [Genesis 1:5](ref:GEN.1.5)\n"
    "- [Genesis 2:3](ref:GEN.2.3)\n"
    "- [Exodus 1:1-2](ref:EXO.1.1-2)"
)


def test_a_day_is_a_heading_over_its_readings() -> None:
    found = plan(run())
    assert found.ok, (found.errors, found.hygiene)
    assert found.document == {
        "slug": "reading-plan-1",
        "kind": "reading-plan",
        "title": "A Made-up Reading Plan",
        "ordinal": 1,
        "text": EXPECTED_PLAN,
    }
    assert (len(found.days), found.readings, found.links) == (2, 8, 9)
    assert (found.months, found.capitals) == (2, 1)


def test_a_book_change_and_a_part_verse_letter() -> None:
    found = plan(run())
    assert found.cross_book == ["Genesis 2:2—Exodus 1:1"]
    assert found.part_verse == ["Exodus 1:2a"]
    assert found.shapes == {
        "verses in one chapter": 2,
        "across chapters": 1,
        "into the next book": 1,
        "a verse": 4,
    }
    assert found.evidence == {"agrees": 8}


def test_a_reading_into_a_book_that_doesnt_follow_blocks() -> None:
    pages = {**BIBLE, **FRONT, **PG}
    wrong = "Genesis 2:2—Leviticus 1:1"
    pages[PLAN] = [
        dataclasses.replace(i, text=wrong) if i.text.startswith("Genesis 2:2") else i
        for i in pages[PLAN]
    ]
    found = plan(run(pages))
    assert not found.ok and any("doesn't follow" in e for e in found.errors)


def test_a_target_naming_no_verse_blocks() -> None:
    pages = {**BIBLE, **FRONT, **PG}
    pages[PLAN] = [
        dataclasses.replace(i, text="Genesis 1:99") if i.text == "Genesis 1:5" else i
        for i in pages[PLAN]
    ]
    found = plan(run(pages))
    assert not found.ok and any("no verse" in e for e in found.errors)


def test_a_link_page_that_isnt_the_readings_blocks() -> None:
    pages = {**BIBLE, **FRONT, **PG}
    pages[PLAN] = [
        dataclasses.replace(i, link=EXO) if i.text == "Genesis 1:4" else i for i in pages[PLAN]
    ]
    found = plan(run(pages))
    assert not found.ok and found.evidence["unexplained"] == 1


# --- Personal Gold's authors -------------------------------------------------------------------


def test_author_notes_and_credits_tied_to_their_articles() -> None:
    found = authors(run())
    assert found.ok, (found.errors, found.hygiene)
    assert found.document == {
        "slug": "about-1",
        "kind": "about",
        "title": "Personal Gold",
        "ordinal": 1,
        "text": (
            "## A MADE-UP SUBTITLE\n\n"
            "**Some Author** wrote made-up books and runs to the margin of the page.\n\n"
            "## PERSONAL GOLD INDEX\n\n"
            "**A Caps Title**\\\nSome Author\n\n"
            "Some Author, *A Made-up Book* (Press, 1999), p. 1.\n\n"
            "**Another Title**\\\nOther Writer\n\n"
            "Taken from a made-up source. www.example.com."
        ),
    }
    assert [n.article.page for n in found.notes if n.article] == [PG_ARTICLE]
    assert [c.article.page for c in found.credits if c.article] == [PG_ARTICLE, PG_ARTICLE + 1]
    assert [(n, a.page) for n, a in found.without_note] == [(2, PG_ARTICLE + 1)]


def test_an_author_note_naming_no_article_blocks() -> None:
    pages = {**BIBLE, **FRONT, **PG}
    pages[PG_AUTHORS_PAGE] = [
        dataclasses.replace(i, text="Nobody Known") if i.text == "Some Author" else i
        for i in pages[PG_AUTHORS_PAGE]
    ]
    found = authors(run(pages))
    assert not found.ok and any("no one article ties to" in e for e in found.errors)


# --- the loader and the payload ------------------------------------------------------------------


def _all(r: Run) -> list[dict[str, object]]:
    f, p, a = front_matter(r), plan(r), authors(r)
    assert p.document is not None and a.document is not None
    return [*f.documents, p.document, a.document]


def test_the_loader_takes_every_document(tmp_path: Path) -> None:
    path = tmp_path / "EMB.json"
    path.write_text(json.dumps({"translation": "EMB", "documents": _all(run())}), "utf-8")
    seeds = parse_canonical_books(load_canonical_books_text())
    aliases = {alias: s.id for s in seeds for alias in s.aliases}
    _, rows, images = parse_documents_file(
        path, 1, frozenset({"EMB"}), aliases, {"EMB": frozenset()}
    )
    assert [row[2] for row in rows] == [  # (id, translation, slug, …)
        *(f"front-matter-{n}" for n in range(1, 6)),
        "reading-plan-1",
        "about-1",
    ]
    assert not images


def test_the_same_pdf_gives_byte_identical_documents() -> None:
    assert json.dumps(_all(run())) == json.dumps(_all(run()))


# --- the EPUB witness ----------------------------------------------------------------------------


def _witnessed(r: Run) -> Witnessed:
    witnessed = Witnessed()
    for part in (front_matter(r).witnessed, plan(r).witnessed, authors(r).witnessed):
        witnessed.extend(part)
    return witnessed


def _flat(witnessed: Witnessed, edit: dict[str, str] | None = None) -> str:
    """The EPUB as one run of text: each part's PDF text, with the titles and contents a
    witness passes over between them."""
    parts = ["CONTENTS A Made-up Preface"]
    for key in witnessed.order:
        parts += ["A MADE-UP TITLE", (edit or {}).get(key[0], witnessed.texts[key])]
    return "   ".join(parts)


def _verdicts(r: Run, edit: dict[str, str] | None = None) -> tuple[dict[str, Verdict], set[str]]:
    witnessed = _witnessed(r)
    epub = epub_cut(_flat(witnessed, edit), witnessed)
    cross = cross_check(witnessed, epub, r.doc, verse_texts(r.result))
    return {f.key[0]: f.verdict for f in cross.findings}, {k[0] for k in epub.damaged}


def test_the_epub_agrees_part_by_part() -> None:
    r = run()
    verdicts, damaged = _verdicts(r)
    keys = [k[0] for k in _witnessed(r).order]
    assert keys == [
        "FRONT 1 §1",
        "FRONT 2 §1",
        "FRONT 2 §2",
        "FRONT 3 §1",
        "FRONT 4 §1",
        "FRONT 4 §2",
        "FRONT 5 §1",
        "PLAN day 1",
        "PLAN day 2",
        "PG AUTHOR 1",
        "PG CREDIT 1",
        "PG CREDIT 2",
    ]
    assert set(verdicts.values()) == {Verdict.AGREE} and not damaged


def test_a_word_the_epub_lacks_is_open_unless_visibly_damaged() -> None:
    r = run()
    witnessed = _witnessed(r)
    text = witnessed.texts[("FRONT 2 §2", 0, 1)]
    verdicts, damaged = _verdicts(r, {"FRONT 2 §2": text.replace("on to the margin ", "")})
    assert verdicts["FRONT 2 §2"] is Verdict.OPEN and not damaged
    scrap = text.replace("on to the margin ", f"on {BREAK}")  # lost at a visible break
    verdicts, damaged = _verdicts(r, {"FRONT 2 §2": scrap})
    # still open, but in visibly damaged EPUB text: listed for reference, not a failure
    assert verdicts["FRONT 2 §2"] is Verdict.OPEN and damaged == {"FRONT 2 §2"}


def test_an_opening_the_epub_lost_runs_into_the_part_before() -> None:
    r = run()
    witnessed = _witnessed(r)
    lost = witnessed.texts[("PLAN day 2", 0, 1)].replace("Firstmonth 2", "Lostmonth 2")
    verdicts, damaged = _verdicts(r, {"PLAN day 2": lost})
    assert verdicts["PLAN day 2"] is Verdict.EPUB_VISIBLE
    assert "PLAN day 1" in damaged


def test_an_opening_the_epub_ran_together_is_found_and_damaged() -> None:
    r = run()
    witnessed = _witnessed(r)
    fused = witnessed.texts[("PLAN day 2", 0, 1)].replace("Firstmonth 2", "xyFirstmonth2")
    _, damaged = _verdicts(r, {"PLAN day 2": fused})
    assert "PLAN day 2" in damaged and "PLAN day 1" not in damaged


def test_a_mark_the_epub_set_apart_still_finds_its_part() -> None:
    """A dropped-text mark and a space inside the opening words ("Name␀ ,"): the part is found,
    marked damaged, and its words agree once the EPUB's spacing closes up."""
    r = run()
    witnessed = _witnessed(r)
    spaced = witnessed.texts[("PG CREDIT 1", 0, 1)].replace("Author,", f"Author{BREAK} ,")
    verdicts, damaged = _verdicts(r, {"PG CREDIT 1": spaced})
    assert verdicts["PG CREDIT 1"] is Verdict.AGREE and "PG CREDIT 1" in damaged
    assert verdicts["PG AUTHOR 1"] is Verdict.AGREE and "PG AUTHOR 1" not in damaged
