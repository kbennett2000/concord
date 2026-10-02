"""Builders for synthetic ``pdftohtml -xml`` documents (made-up text only).

A synthetic book places the 66 canonical books in the outline, ``BOOK_PAGES`` apart from
``FIRST_BOOK_PAGE``, followed by a "… Textual Notes" header, a feature index and the study
notes index — the landmarks ``layout.find_layout`` looks for. Tests fill a few books' pages
with ``T`` items; every other book stays empty. The textual notes go on ``NOTES_PAGE`` (whose
first block, "Genesis 1 Textual Notes", the kit always prints) and the pages after it; the
study notes on ``STUDY_NOTES_PAGE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from bible_core.seed import load_canonical_books_text, parse_canonical_books

FIRST_BOOK_PAGE = 100
BOOK_PAGES = 10
CODES = [
    s.id
    for s in sorted(
        parse_canonical_books(load_canonical_books_text()), key=lambda s: s.canonical_order
    )
]
NAMES = {s.id: s.name for s in parse_canonical_books(load_canonical_books_text())}
NOTES_PAGE = FIRST_BOOK_PAGE + BOOK_PAGES * len(CODES)
FEATURES_PAGE = NOTES_PAGE + 20
# the feature sections (V8-S3a): each index's page; "Feature Index" (where the S1 callouts and
# boxes point) stays a section of its own
MWG_PAGE = FEATURES_PAGE + 3
SYSK_PAGE = FEATURES_PAGE + 8
PG_AUTHORS_PAGE = FEATURES_PAGE + 13
PG_PAGE = FEATURES_PAGE + 14
# V8-S3b: the topics' section and the Perspectives index, after Personal Gold
WBSA_PAGE = FEATURES_PAGE + 20
PERSP_PAGE = FEATURES_PAGE + 27
STUDY_PAGE = FEATURES_PAGE + 30
STUDY_NOTES_PAGE = STUDY_PAGE + 1
PAGE_BOX = 'top="0" left="0" height="496" width="378"'


def start(code: str) -> int:
    """A book's first page in the synthetic book."""
    return FIRST_BOOK_PAGE + BOOK_PAGES * CODES.index(code)


@dataclass(frozen=True)
class T:
    """One ``<text>`` item."""

    text: str
    top: int
    left: int = 38
    size: int = 12
    blue: bool = False
    bold: bool = False
    italic: bool = False
    link: int | None = None
    width: int | None = None


# -- common item shapes ---------------------------------------------------------------


def header(code: str, chapter: int, top: int = 60) -> list[T]:
    """A chapter header: blue book name (size 15) and numeral (size 23), linking home."""
    home = start(code)
    return [
        T("Book", top + 5, 38, 15, blue=True, link=home),
        T(str(chapter), top, 90, 23, blue=True, link=home),
    ]


def vnum(n: str, top: int, left: int = 38) -> T:
    return T(n, top - 2, left, 7, width=7)


def body(text: str, top: int, left: int = 46, width: int | None = None) -> T:
    return T(text, top, left, width=width)


def full(text: str, top: int, left: int = 38) -> T:
    """A body line that runs to the right margin (justified prose)."""
    return T(text, top, left, width=341 - left)


def heading(text: str, top: int) -> T:
    return T(text, top, 38, bold=True, italic=True)


def italic(text: str, top: int, left: int = 38) -> T:
    return T(text, top, left, italic=True)


def marker(top: int, left: int, page: int = NOTES_PAGE) -> T:
    return T("*", top, left, blue=True, link=page)


def callout(text: str, top: int) -> T:
    return T(text, top, 250, blue=True, bold=True, link=FEATURES_PAGE + 1)


def notes_header(*parts: str, top: int = 43) -> list[T]:
    """A textual-notes block header (bold, size 23); several parts make a wrapped one."""
    return [T(part, top + 28 * n, 38, 23, bold=True) for n, part in enumerate(parts)]


def label(text: str, top: int, page: int) -> T:
    """A note's label: blue bold, linking back to the verse's page."""
    return T(text, top, 38, blue=True, bold=True, link=page)


def title_label(chapter: int, top: int, page: int) -> list[T]:
    """A psalm-title note's label: "N:" and a small-caps "TITLE"."""
    return [
        T(f"{chapter}:", top, 38, blue=True, bold=True, link=page),
        T("TITLE", top + 3, 47, 7, bold=True, link=page),
    ]


def study_head(abbreviation: str, reference: str, top: int, page: int) -> list[T]:
    """A study note's heading: a bold book abbreviation and a blue bold reference."""
    return [
        T(f"{abbreviation} ", top, 38, bold=True),
        T(reference, top, 63, blue=True, bold=True, link=page),
    ]


def link(text: str, top: int, left: int, page: int | None, width: int | None = None) -> T:
    """A reference a study note links (blue, not bold)."""
    return T(text, top, left, blue=True, link=page, width=width)


def callout_number(n: str, top: int, page: int = STUDY_NOTES_PAGE, left: int = 38) -> T:
    """A blue verse number: the book calls out a study note here."""
    return T(n, top - 2, left, 7, blue=True, link=page, width=7)


def box(top: int, ref_page: int) -> list[T]:
    """A Perspectives box: label, quoted text (with small caps), reference, attribution."""
    return [
        T("PERSPECTIVES", top, 61, 9, blue=True, link=FEATURES_PAGE + 2),
        T("The quoted line about the L", top + 20, 61, width=200),
        T("ORD", top + 23, 261, 7),
        T(" and more.", top + 20, 280),
        T("BOOKNAME 1:2-3", top + 40, 61, 7, blue=True, link=ref_page),
        T("A wise saying from someone.", top + 60, 61),
        T("SOMEONE FAMOUS", top + 80, 61, 7),
    ]


# -- document assembly ----------------------------------------------------------------


def _fonts(pages: dict[int, list[T]]) -> dict[tuple[int, bool], int]:
    specs: dict[tuple[int, bool], int] = {}
    for items in pages.values():
        for item in items:
            specs.setdefault((item.size, item.blue), len(specs))
    for extra in ((12, False), (23, False)):
        specs.setdefault(extra, len(specs))
    return specs


def _text(item: T, fonts: dict[tuple[int, bool], int]) -> str:
    inner = escape(item.text, quote=False)
    if item.italic:
        inner = f"<i>{inner}</i>"
    if item.bold:
        inner = f"<b>{inner}</b>"
    if item.link is not None:
        inner = f'<a href="book.html#{item.link}">{inner}</a>'
    width = item.width if item.width is not None else max(4, len(item.text) * 5)
    font = fonts[(item.size, item.blue)]
    return (
        f'<text top="{item.top}" left="{item.left}" width="{width}" height="11" '
        f'font="{font}">{inner}</text>'
    )


def document(pages: dict[int, list[T]], extra_outline: list[tuple[int, str]] | None = None) -> str:
    """A whole synthetic pdftohtml document around ``pages`` (page number → items)."""
    pages = dict(pages)
    pages[NOTES_PAGE] = [T("Genesis 1 Textual Notes", 43, 38, 23), *pages.get(NOTES_PAGE, [])]
    fonts = _fonts(pages)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<pdf2xml producer="poppler" version="test">']
    declared: set[int] = set()
    for number in range(1, STUDY_PAGE + 2):
        out.append(f'<page number="{number}" position="absolute" {PAGE_BOX}>')
        for (size, blue), fid in fonts.items():
            if fid not in declared:
                colour = "#0000ee" if blue else "#000000"
                out.append(f'<fontspec id="{fid}" size="{size}" family="Times" color="{colour}"/>')
                declared.add(fid)
        for item in pages.get(number, []):
            out.append(_text(item, fonts))
        out.append("</page>")
    outline = [(start(code), NAMES[code]) for code in CODES]
    outline += [
        (FEATURES_PAGE, "Feature Index"),
        (MWG_PAGE, "Men, Women, and God Index"),
        (SYSK_PAGE, "Someone You Should Know Index"),
        (PG_AUTHORS_PAGE, "Personal Gold Author Index"),
        (PG_PAGE, "Personal Gold Index"),
        (WBSA_PAGE, "What the Bible Says About Index"),
        (PERSP_PAGE, "Perspectives Index"),
        (STUDY_PAGE, "Study Notes Index"),
    ]
    outline += extra_outline or []
    out.append("<outline>")
    out += [f'<item page="{page}">{escape(title)}</item>' for page, title in outline]
    out.append("</outline>")
    out.append("</pdf2xml>")
    return "\n".join(out)


def nav(code: str, chapters: int, top: int = 72) -> list[T]:
    """A book's chapter-navigation list on its first page."""
    items = [T("Introduction", top, 38, blue=True, link=start(code) + 1)]
    items += [
        T(str(n), top, 100 + 10 * n, blue=True, link=start(code) + 1)
        for n in range(1, chapters + 1)
    ]
    return items


def verse_texts(result: Any) -> dict[tuple[str, int, int], str]:
    return {
        (b.code, c.number, v.number): v.text
        for b in result.books
        for c in b.chapters
        for v in c.verses
    }


def parse_notes(pages: dict[int, list[T]], public: tuple[str, ...] = ()) -> tuple[Any, Any]:
    """Parse a synthetic document's Bible text, then its notes (``ParseResult``,
    ``NotesResult``)."""
    from emb_convert.clean import Fixes, PublicWords
    from emb_convert.layout import find_layout
    from emb_convert.notes import build_notes
    from emb_convert.pdfxml import parse_pdf_xml
    from emb_convert.skeleton import load_skeleton
    from emb_convert.text import parse_bible

    doc = parse_pdf_xml(document(pages))
    layout = find_layout(doc)
    words = PublicWords(public)
    result = parse_bible(doc, layout, Fixes(), words)
    return result, build_notes(doc, layout, result, words, load_skeleton())


def parse(
    pages: dict[int, list[T]],
    fixes: Any = None,
    public: tuple[str, ...] = (),
) -> Any:
    """Parse a synthetic document's Bible text (``ParseResult``)."""
    from emb_convert.clean import Fixes, PublicWords
    from emb_convert.layout import find_layout
    from emb_convert.pdfxml import parse_pdf_xml
    from emb_convert.text import parse_bible

    doc = parse_pdf_xml(document(pages))
    return parse_bible(doc, find_layout(doc), fixes or Fixes(), PublicWords(public))
