"""EMB's book introductions (V8-S5b; docs/v8/SPEC.md §4.3, §4.4, ADR-0012).

Each of the 66 books opens with an introduction: after the book's navigation page, before its
first chapter. The text pass hands over its lines (``text.Diagnostics.intros``: callout lines
and the heading above chapter 1 already set aside by the text pass's own rules). Everything here
is read from print style, never from words — no book text is held in this module:

- the **title**: the one 23-point line, first;
- a **section head**: a 12-point bold line at the margin, in capitals; the section runs to the
  next head;
- at the margin, 12-point **text**: a line and the lines its wrap carries on make one unit; a
  run of two or more units is a list (one entry per unit, as the book prints them, with no
  bullet), a single unit a paragraph;
- a **label**: a bold line at the margin, 9 or 7 points. A 9-point label that carries a
  reference opens a **quotation**: the indented lines after it (61 points prose, 46 a poetic line
  each), gaps and all, are one block quote. Any other label is a sub-head over its indented
  paragraphs (a 46-point line there is quoted poetry too);
- a **caption**: a 7-point line at the margin, set directly above the introduction's **figure**
  (its one image under chart size — the image census's "introduction figure"). The caption
  becomes the figure's alt text, and the figure's bytes are written as the PDF stores them;
- the **What's the Point box**: a centred 7-point label, the book's name and "?" on the next
  line (the document's title in normal case; the 23-point title is the same name set in lower
  case), an ornament line of "+" signs (dropped and counted), then the centred point;
- the **timeline**, after the box: 61-point lines, a 9-point date (small capitals at 7) above a
  12-point bold event. An event within a line's pitch below its date belongs to it, and an event
  line within a line's pitch below another (or over a page turn from a wrapped one) continues
  it; anything else starts an entry of its own.

Inline text is the notes' (``notetext``: broken words, small caps, escapes) and every link into
the Bible is a ``ref:`` link, resolved and checked as the articles' are (``notes.link_spans``).
Anything else a line can be is an error, so nothing is guessed silently.
"""

from __future__ import annotations

import dataclasses
import re
import statistics
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from bible_core.assets import MAX_ASSET_BYTES, ImageError, image_header

from emb_convert.charts import CHART_HEIGHT, ICON_WIDTH
from emb_convert.clean import Fixes, Vocabulary, unspace
from emb_convert.crosscheck import CrossCheck, cross_check_notes
from emb_convert.epub import BREAK, IMAGE, EpubBible
from emb_convert.layout import Layout
from emb_convert.lines import Line
from emb_convert.notes import (
    HYGIENE,
    Context,
    LinkFinding,
    broken_words,
    link_spans,
    spaced,
)
from emb_convert.notetext import (
    NoteText,
    Piece,
    assemble,
    emphasis_ok,
    plain_of,
    plain_text,
    relink,
    render,
)
from emb_convert.pdfxml import PdfDocument, TextItem
from emb_convert.study import LinkRun, link_runs
from emb_convert.text import ParseResult

KIND = "book-introduction"
TITLE_SIZE = 23
TEXT_SIZE = 12
LABEL_SIZE = 9
SMALL_SIZE = 7
MARGIN = 41  # a line starting at or left of this starts at the margin (38)
POETRY = 52  # … of this (46): a quoted line of poetry
INDENT = 64  # … of this (61): an indented block — a quotation's prose, a paragraph, the timeline
CENTRE = 84  # right of this: a centred line (the What's the Point box)
WRAP_RIGHT = 330  # a line reaching this x ran to the right margin
GAP = 20  # more than a line's pitch (14–15 points)
ENTRY_PITCH = 16  # a timeline event sits 11 points below its date

Key = tuple[str, int, int]

_ORNAMENT = re.compile(r"^[+\s]+$")
# A timeline date the book queries, "997(?)": a mark against a digit, as printed — kept out of
# the punctuation-spacing check.
_QUERIED_DATE = re.compile(r"(?<=\d)\(\?\)")
_LETTERS = re.compile(r"\W+")
_WS_ALL = re.compile(r"\s+")

# Links read in their sentence whose book's own target page disagrees (none so far).
REVIEWED_INTRODUCTION_LINKS: frozenset[tuple[str, str]] = frozenset()


def key(book: str, section: int) -> Key:
    """A section's key in the cross-check: its book and its place (1 the first head's)."""
    return (f"INTRO {book} §{section}", 0, 1)


def sections(lines: Sequence[Line]) -> list[list[Line]]:
    """An introduction's lines split where a section head or the What's the Point box opens."""
    out: list[list[Line]] = []
    for line in lines:
        if not out or _is_head(line) or _is_box_label(line):
            out.append([line])
        else:
            out[-1].append(line)
    return out


def slug(book: str) -> str:
    return f"introduction-{book.lower()}"


# --- the figures -------------------------------------------------------------------------------


@dataclass(slots=True)
class Figure:
    """An introduction figure: where it stands and its bytes as the PDF stores them."""

    book: str
    page: int
    top: int
    data: bytes = b""
    media_type: str = ""
    width: int = 0
    height: int = 0

    @property
    def name(self) -> str:
        extension = "png" if self.media_type == "image/png" else "jpg"
        return f"reading-time-{self.book.lower()}.{extension}"


def read_figures(doc: PdfDocument, layout: Layout) -> tuple[list[Figure], list[str]]:
    """Every introduction figure in the PDF — the census's kind: in a book's text, on a page
    with text, the text column's width, under chart height — with its bytes read while the
    files exist."""
    text_pages = {i.page for i in doc.items if i.stripped}
    figures: list[Figure] = []
    errors: list[str] = []
    for image in doc.images:
        in_text = layout.bible_start <= image.page < layout.notes_start
        if not in_text or image.page not in text_pages:
            continue
        if image.width < ICON_WIDTH or image.height >= CHART_HEIGHT:
            continue
        book = layout.book_at(image.page)
        assert book is not None
        figure = Figure(book.code, image.page, image.top)
        try:
            figure.data = image.src.read_bytes()
            figure.media_type, figure.width, figure.height = image_header(figure.data)
        except (OSError, ImageError) as exc:
            errors.append(f"the figure on p{image.page} can't be read ({exc})")
            continue
        if len(figure.data) > MAX_ASSET_BYTES:
            errors.append(
                f"the figure on p{image.page} is {len(figure.data):,} bytes, over the limit"
            )
        figures.append(figure)
    return figures, errors


# --- the layout --------------------------------------------------------------------------------


class Kind(Enum):
    HEAD = "head"
    PARAGRAPH = "paragraph"
    LIST = "list"
    LABEL = "label"
    QUOTE = "quotation"
    FIGURE = "figure"
    POINT = "point"
    TIMELINE = "timeline"


@dataclass(slots=True)
class Entry:
    """One timeline entry: its date line and its event's lines (either may be absent)."""

    date: Line | None = None
    event: list[Line] = field(default_factory=list[Line])


@dataclass(slots=True)
class Block:
    kind: Kind
    groups: list[list[Line]] = field(default_factory=list[list[Line]])
    poetry: list[bool] = field(default_factory=list[bool])  # a quotation's parts
    entries: list[Entry] = field(default_factory=list[Entry])  # the timeline
    quotes: bool = False  # a label that opens a quotation


@dataclass(slots=True)
class Introduction:
    book: str
    order: int
    lines: list[Line]  # what the introduction prints, the title aside
    title_line: Line | None = None
    blocks: list[Block] = field(default_factory=list[Block])
    figure: Figure | None = None
    set_aside: list[Line] = field(default_factory=list[Line])  # bold-italic: chapter 1's heading
    ornaments: int = 0
    errors: list[str] = field(default_factory=list[str])

    @property
    def heads(self) -> list[Line]:
        return [b.groups[0][0] for b in self.blocks if b.kind is Kind.HEAD]


def _nonblank(line: Line) -> list[TextItem]:
    return line.nonblank


def _left(line: Line) -> int:
    return min(i.left for i in _nonblank(line))


def _wrapped(line: Line) -> bool:
    return line.right >= WRAP_RIGHT


def _gap(before: Line | None, line: Line) -> bool:
    return before is not None and before.page == line.page and line.top - before.top > GAP


def _all(line: Line, test: Callable[[TextItem], bool]) -> bool:
    return all(test(i) for i in _nonblank(line))


def _is_title(line: Line) -> bool:
    return _all(line, lambda i: i.size == TITLE_SIZE)


def _is_set_aside(line: Line) -> bool:
    return _all(line, lambda i: i.bold and i.italic)


def _is_head(line: Line) -> bool:
    return (
        _left(line) <= MARGIN
        and _all(line, lambda i: i.size == TEXT_SIZE and i.bold and not i.italic and not i.blue)
        and line.text.upper() == line.text
    )


def _is_label(line: Line) -> bool:
    return _left(line) <= MARGIN and _all(
        line, lambda i: i.bold and not i.italic and i.size in (LABEL_SIZE, SMALL_SIZE)
    )


def _is_caption(line: Line) -> bool:
    return _left(line) <= MARGIN and _all(line, lambda i: i.size == SMALL_SIZE and not i.bold)


def _is_box_label(line: Line) -> bool:
    return _left(line) > CENTRE and _all(line, lambda i: i.size == SMALL_SIZE and not i.bold)


def _is_centred_text(line: Line) -> bool:
    return _left(line) > MARGIN and _all(line, lambda i: i.size == TEXT_SIZE and not i.bold)


def _is_margin_text(line: Line) -> bool:
    first = _nonblank(line)[0]
    return _left(line) <= MARGIN and first.size == TEXT_SIZE and not _all(line, lambda i: i.bold)


def _band(line: Line) -> str:
    left = _left(line)
    if left <= MARGIN:
        return "margin"
    if left <= POETRY:
        return "poetry"
    if left <= INDENT:
        return "indent"
    return "centre"


def _is_date(line: Line) -> bool:
    return (
        _band(line) == "indent"
        and _all(line, lambda i: i.size in (LABEL_SIZE, SMALL_SIZE) and not i.bold)
        and any(i.size == LABEL_SIZE for i in _nonblank(line))
    )


def _is_event(line: Line) -> bool:
    return _band(line) == "indent" and _all(line, lambda i: i.size == TEXT_SIZE and i.bold)


class _Segmenter:
    """One introduction's lines (and its figure, where it stands) → blocks."""

    def __init__(self, intro: Introduction) -> None:
        self.intro = intro
        self.blocks = intro.blocks
        self.mode = "section"
        self.current: Block | None = None
        self.units: list[list[Line]] = []  # a margin run's units
        self.before: Line | None = None
        self.quotes = False  # under a label that opens a quotation
        self.caption: Line | None = None

    def error(self, line: Line, what: str) -> None:
        self.intro.errors.append(f"{self.intro.book} p{line.page} top {line.top}: {what}")

    # -- closing what is open

    def close(self) -> None:
        if self.units:
            if len(self.units) >= 2:
                self.blocks.append(Block(Kind.LIST, self.units))
            else:
                self.blocks.append(Block(Kind.PARAGRAPH, self.units))
            self.units = []
        self.current = None

    def open(self, block: Block) -> Block:
        self.close()
        self.blocks.append(block)
        self.current = block
        return block

    # -- driving

    def run(self, lines: list[Line], figure: Figure | None) -> None:
        stream: list[Line | Figure] = list(lines)
        if figure is not None:
            at = next(
                (
                    n
                    for n, line in enumerate(lines)
                    if (line.page, line.top) > (figure.page, figure.top)
                ),
                len(lines),
            )
            stream.insert(at, figure)
        for element in stream:
            if isinstance(element, Figure):
                self.figure(element)
                continue
            if self.caption is not None:
                self.error(self.caption, "a caption with no figure under it")
                self.caption = None
            self.line(element)
            self.before = element
        if self.caption is not None:
            self.error(self.caption, "a caption with no figure under it")
        self.close()

    def figure(self, figure: Figure) -> None:
        if self.caption is None or self.mode != "section":
            self.intro.errors.append(f"{self.intro.book}: its figure has no caption above it")
            return
        self.open(Block(Kind.FIGURE, [[self.caption]]))
        self.caption = None
        self.close()

    def line(self, line: Line) -> None:
        if _is_head(line):
            self.mode = "section"
            self.quotes = False
            self.open(Block(Kind.HEAD, [[line]]))
            self.close()
            return
        if _is_box_label(line):
            self.mode = "box"
            self.quotes = False
            self.open(Block(Kind.POINT, [[line]]))
            return
        if self.mode == "box":
            self.box_line(line)
        elif self.mode == "timeline":
            self.timeline_line(line)
        else:
            self.section_line(line)

    def box_line(self, line: Line) -> None:
        block = self.current
        if block is not None and block.kind is Kind.POINT and len(block.groups[0]) == 1:
            if not _is_centred_text(line) or not line.text.strip().endswith("?"):
                self.error(line, "the What's the Point box names no book")
            block.groups[0].append(line)  # its heading: the label, then the name
            return
        if _is_date(line) or _is_event(line):
            self.mode = "timeline"
            self.open(Block(Kind.TIMELINE))
            self.timeline_line(line)
            return
        if not _is_centred_text(line):
            self.error(line, "a line the What's the Point box doesn't explain")
            return
        if block is not None and block.kind is Kind.POINT:
            block.groups.append([line])  # the point
        elif block is not None and block.kind is Kind.PARAGRAPH:
            block.groups[0].append(line)
        else:
            self.error(line, "the point comes before its box's heading")

    def timeline_line(self, line: Line) -> None:
        block = self.current
        assert block is not None and block.kind is Kind.TIMELINE
        entries = block.entries
        if _is_date(line):
            entries.append(Entry(date=line))
            return
        if not _is_event(line):
            self.error(line, "a line the timeline doesn't explain")
            return
        last = entries[-1] if entries else None
        previous = last.event[-1] if last is not None and last.event else None
        if (
            last is not None
            and previous is not None
            and (
                (previous.page == line.page and line.top - previous.top <= ENTRY_PITCH)
                or (previous.page != line.page and _wrapped(previous))
            )
        ):
            last.event.append(line)  # an event's second line
        elif (
            last is not None
            and not last.event
            and last.date is not None
            and (line.page != last.date.page or line.top - last.date.top <= ENTRY_PITCH)
        ):
            last.event.append(line)
        else:
            entries.append(Entry(event=[line]))

    def section_line(self, line: Line) -> None:
        if not self.blocks:
            self.error(line, "text before the first section head")
        if _is_caption(line):
            self.close()
            self.caption = line
            return
        if _is_label(line):
            block = self.current
            if (
                block is not None
                and block.kind is Kind.LABEL
                and self.before is not None
                and _wrapped(self.before)
            ):
                block.groups[0].append(line)
            else:
                block = self.open(Block(Kind.LABEL, [[line]]))
            block.quotes = any(i.blue for i in _nonblank(line)) and any(
                i.size == LABEL_SIZE for i in _nonblank(line)
            )
            self.quotes = block.quotes
            return
        if _is_margin_text(line):
            if self.current is not None:
                self.close()
            before = self.before
            if (
                self.units
                and before is not None
                and self.units[-1][-1] is before
                and _wrapped(before)
                and not _gap(before, line)
            ):
                self.units[-1].append(line)
            else:
                self.units.append([line])
            return
        band = _band(line)
        if band in ("poetry", "indent") and _nonblank(line)[0].size == TEXT_SIZE:
            self.indented(line, poetry=band == "poetry")
            return
        self.error(line, f"a line at left {_left(line)} the introduction's layout doesn't explain")

    def indented(self, line: Line, *, poetry: bool) -> None:
        before = self.before
        block = self.current
        if self.units:
            self.close()
            block = None
        if self.quotes or poetry:
            if block is None or block.kind is not Kind.QUOTE:
                block = self.open(Block(Kind.QUOTE))
            new_part = (
                not block.groups
                or block.poetry[-1] != poetry
                or _gap(before, line)
                or (not poetry and before is not None and not _wrapped(before))
            )
            if new_part:
                block.groups.append([line])
                block.poetry.append(poetry)
            else:
                block.groups[-1].append(line)
            return
        if (
            block is not None
            and block.kind is Kind.PARAGRAPH
            and before is not None
            and block.groups[-1][-1] is before
            and _wrapped(before)
            and not _gap(before, line)
        ):
            block.groups[-1].append(line)
        else:
            self.open(Block(Kind.PARAGRAPH, [[line]]))


def _is_ornament(line: Line) -> bool:
    return bool(_ORNAMENT.match(line.text)) and "+" in line.text


def segment(book: str, order: int, lines: list[Line], figures: Sequence[Figure]) -> Introduction:
    """One introduction's printed lines → its title, blocks and figure."""
    intro = Introduction(book, order, [])
    for line in lines:
        if not _nonblank(line):
            continue
        if _is_title(line):
            if intro.title_line is not None or intro.lines:
                intro.errors.append(f"{book} p{line.page}: a second title, or a title not first")
            intro.title_line = line
        elif _is_set_aside(line):
            intro.set_aside.append(line)
        elif _is_ornament(line):  # the What's the Point box's "+ + +": decoration
            intro.ornaments += 1
        else:
            intro.lines.append(line)
    if intro.title_line is None:
        intro.errors.append(f"{book}: no title")
    if intro.lines:
        first = (intro.lines[0].page, intro.lines[0].top)
        last = (intro.lines[-1].page, intro.lines[-1].top)
        mine = [f for f in figures if f.book == book and first <= (f.page, f.top) <= last]
        if len(mine) == 1:
            intro.figure = mine[0]
        else:
            intro.errors.append(f"{book}: {len(mine)} figures in its introduction")
    _Segmenter(intro).run(intro.lines, intro.figure)
    return intro


class _Labels:
    """A bold label breaks a word at a glyph gap anywhere in it, as a justified line does
    ("AB CD" for "ABCD", measured once): its items are read with the notes' rule — joined where
    the pieces make a word and aren't words themselves. The fixed lines keep their link runs."""

    def __init__(self, vocabulary: Vocabulary, run_of: dict[int, int], counts: Counter[str]):
        self.vocabulary = vocabulary
        self.run_of = run_of
        self.counts = counts
        self.cache: dict[int, Line] = {}

    def lines(self, lines: Sequence[Line], fixes: Fixes) -> list[Line]:
        if not fixes.letter_spacing:
            return list(lines)
        return [self._line(line) if _is_label(line) else line for line in lines]

    def _line(self, line: Line) -> Line:
        cached = self.cache.get(id(line))
        if cached is not None:
            return cached
        items: list[TextItem] = []
        for item in line.items:
            fixed = None
            if item.stripped:
                fixed = unspace(
                    item.text,
                    self.vocabulary,
                    italic=False,
                    first=True,
                    justified=True,
                    anywhere=True,
                    apostrophe_splits=False,
                )
            if fixed is None:
                items.append(item)
                continue
            new = dataclasses.replace(item, text=fixed)
            if id(item) in self.run_of:
                self.run_of[id(new)] = self.run_of[id(item)]
            self.counts["letter-spaced"] += 1
            items.append(new)
        cached = Line(line.page, line.top, items)
        self.cache[id(line)] = cached
        return cached


# --- Markdown ----------------------------------------------------------------------------------

Inline = Callable[[Sequence[Line]], list[Piece]]


@dataclass(slots=True)
class Written:
    markdown: str
    plain: str  # the text as read, blocks apart by blank lines (hygiene runs on it)
    printed: str  # every character the blocks print, spaces aside (the consistency check)
    title: str
    problems: list[str] = field(default_factory=list[str])


def write(
    intro: Introduction,
    inline: Inline,
    relink_: Callable[[list[Piece]], tuple[list[Piece], list[str]]],
) -> Written:
    """The introduction's blocks as Markdown."""
    out = Written("", "", "", "")
    markdown: list[str] = []
    plain: list[str] = []
    printed: list[str] = []

    def text(lines: Sequence[Line], *, plain_style: bool = False) -> NoteText:
        pieces = inline(lines)
        printed.append(" ".join(p.text for p in pieces))
        if plain_style:  # a head, label or event is bold already; its weight stays out
            pieces = [dataclasses.replace(p, bold=False, italic=False) for p in pieces]
        pieces, targets = relink_(pieces)
        rendered = render(pieces, targets, always=True)
        assert rendered.markdown is not None
        if not emphasis_ok(rendered.markdown):
            out.problems.append("emphasis-flanking")
        if plain_of(rendered.markdown) != rendered.plain:
            out.problems.append("markdown-round-trip")
        return rendered

    def strong(t: NoteText) -> str:
        md = f"**{_md(t)}**"
        if not emphasis_ok(md):
            out.problems.append("emphasis-flanking")
        return md

    for block in intro.blocks:
        kind = block.kind
        if kind is Kind.HEAD:
            t = text(block.groups[0], plain_style=True)
            markdown.append(f"## {_md(t)}")
            plain.append(t.plain)
        elif kind is Kind.PARAGRAPH:
            t = text(block.groups[0])
            markdown.append(_md(t))
            plain.append(t.plain)
        elif kind is Kind.LIST:
            ts = [text(group) for group in block.groups]
            markdown.append("\n".join(f"- {_md(t)}" for t in ts))
            plain.append("\n".join(t.plain for t in ts))
        elif kind is Kind.LABEL:
            t = text(block.groups[0], plain_style=True)
            markdown.append(strong(t))
            plain.append(t.plain)
        elif kind is Kind.QUOTE:
            parts: list[str] = []
            for group, poetry in zip(block.groups, block.poetry, strict=True):
                if poetry:
                    ts = [text([line]) for line in group]
                    parts.append("\\\n".join(f"> {_md(t)}" for t in ts))
                    plain.append("\n".join(t.plain for t in ts))
                else:
                    t = text(group)
                    parts.append(f"> {_md(t)}")
                    plain.append(t.plain)
            markdown.append("\n>\n".join(parts))
        elif kind is Kind.FIGURE:
            t = text(block.groups[0], plain_style=True)
            assert intro.figure is not None
            markdown.append(f"![{_md(t)}](asset:{intro.figure.name})")
            plain.append(t.plain)
        elif kind is Kind.POINT:
            head = text(block.groups[0], plain_style=True)
            markdown.append(f"## {_md(head)}")
            plain.append(head.plain)
            name_line = block.groups[0][-1]
            out.title = " ".join(name_line.text.split()).rstrip("?").strip()
            if len(block.groups) > 1:
                point = text([line for group in block.groups[1:] for line in group])
                markdown.append(_md(point))
                plain.append(point.plain)
        else:
            items: list[str] = []
            for entry in block.entries:
                lines: list[str] = []  # the entry's printed lines, a wrapped one joined
                if entry.date is not None:
                    date = text([entry.date])
                    lines.append(_md(date))
                    plain.append(date.plain)
                for group in _printed_lines(entry.event):
                    event = text(group, plain_style=True)
                    lines.append(strong(event))
                    plain.append(event.plain)
                items.append("- " + "\\\n  ".join(lines))
            markdown.append("\n".join(items))
    out.markdown = "\n\n".join(markdown)
    out.plain = "\n\n".join(plain)
    out.printed = _WS_ALL.sub("", " ".join(printed))
    return out


def _printed_lines(lines: list[Line]) -> list[list[Line]]:
    """Lines as the book sets them: a wrapped line and the line it runs on to are one."""
    groups: list[list[Line]] = []
    for line in lines:
        if groups and _wrapped(groups[-1][-1]):
            groups[-1].append(line)
        else:
            groups.append([line])
    return groups


def _md(text: NoteText) -> str:
    assert text.markdown is not None
    return text.markdown


def structures(intro: Introduction) -> Counter[str]:
    """What an introduction prints, by kind."""
    counts: Counter[str] = Counter()
    for block in intro.blocks:
        counts[block.kind.value] += 1
        if block.kind is Kind.LIST:
            counts["list items"] += len(block.groups)
        if block.kind is Kind.LABEL:
            counts["quotation labels" if block.quotes else "sub-heads and other labels"] += 1
        if block.kind is Kind.QUOTE:
            counts["quoted paragraphs"] += sum(1 for p in block.poetry if not p)
            counts["quoted lines of poetry"] += sum(
                len(g) for g, p in zip(block.groups, block.poetry, strict=True) if p
            )
        if block.kind is Kind.POINT:
            counts["point lines"] += sum(len(g) for g in block.groups[1:])
        if block.kind is Kind.TIMELINE:
            entries = block.entries
            counts["timeline entries"] += len(entries)
            counts["timeline events on two lines"] += sum(1 for e in entries if len(e.event) > 1)
            counts["timeline events set on two lines, the first not wrapped"] += sum(
                1 for e in entries if len(_printed_lines(e.event)) > 1
            )
            counts["timeline events without a date"] += sum(1 for e in entries if e.date is None)
            counts["timeline dates without an event"] += sum(1 for e in entries if not e.event)
    return counts


# --- the run -----------------------------------------------------------------------------------


@dataclass(slots=True)
class IntroductionFindings:
    """EMB's book introductions (V8-S5b): found, written and checked."""

    introductions: list[Introduction] = field(default_factory=list[Introduction])
    documents: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    figures: list[Figure] = field(default_factory=list[Figure])  # every one in the PDF
    assets: dict[str, bytes] = field(default_factory=dict[str, bytes])
    heads: Counter[str] = field(default_factory=Counter[str])  # each printed head, by count
    head_lists: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    head_order: list[str] = field(default_factory=list[str])  # the heads' one order
    structures: Counter[str] = field(default_factory=Counter[str])
    timelines: int = 0
    words: dict[str, int] = field(default_factory=dict[str, int])
    links: list[LinkFinding] = field(default_factory=list[LinkFinding])
    fixes: Counter[str] = field(default_factory=Counter[str])
    callouts_set_aside: int = 0
    set_aside: int = 0
    ornaments: int = 0
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])
    # for the EPUB cross-check: each introduction's plain text (fixed, raw, one fix alone)
    texts: dict[Key, str] = field(default_factory=dict[Key, str])
    raw: dict[Key, str] = field(default_factory=dict[Key, str])
    solo: dict[str, dict[Key, str]] = field(default_factory=dict[str, dict[Key, str]])
    spans: dict[Key, tuple[int, int]] = field(default_factory=dict[Key, tuple[int, int]])
    captions: dict[str, str] = field(default_factory=dict[str, str])  # book → its caption
    # book → the line opening each section (its head, or the box's label), for the EPUB's split
    section_heads: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    callout_labels: dict[str, list[str]] = field(default_factory=dict[str, list[str]])

    @property
    def unclaimed(self) -> list[Figure]:
        claimed = {id(i.figure) for i in self.introductions if i.figure is not None}
        return [f for f in self.figures if id(f) not in claimed]

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and not self.unclaimed
            and not any(self.hygiene.values())
            and all(f.evidence != "unexplained" for f in self.links)
        )


def build_introductions(
    doc: PdfDocument,
    layout: Layout,
    parse: ParseResult,
    ctx: Context,
    figures: list[Figure],
) -> IntroductionFindings:
    """Every book's introduction → a document, its figure → an asset."""
    found = IntroductionFindings(figures=figures)
    diag = parse.diagnostics
    found.callouts_set_aside = sum(1 for c in diag.feature_callouts if c.in_intro)
    for callout in diag.feature_callouts:
        if callout.in_intro:
            found.callout_labels.setdefault(callout.book, []).append(callout.label)

    def is_link(item: TextItem) -> bool:
        page = item.link_page
        return page is None or layout.bible_start <= page < layout.notes_start

    for book in layout.books:
        lines = diag.intros.get(book.code, [])
        if not lines:
            found.errors.append(f"{book.code}: no introduction")
            continue
        intro = segment(book.code, book.order, lines, figures)
        found.introductions.append(intro)
        found.errors += intro.errors
        found.set_aside += len(intro.set_aside)
        first_headings = {
            _LETTERS.sub("", h.text).casefold()
            for b in parse.books
            if b.code == book.code
            for h in b.chapters[0].headings
        }
        for line in intro.set_aside:
            if _LETTERS.sub("", line.text).casefold() not in first_headings:
                found.errors.append(
                    f"{book.code} p{line.page}: a bold-italic line that isn't chapter 1's heading"
                )
        found.ornaments += intro.ornaments
        if intro.figure is None:
            continue
        name = f"INTRO {book.code}"
        run_of, runs = link_runs(intro.lines, is_link)
        scratch: Counter[str] = Counter()
        labels = _Labels(ctx.vocabulary, run_of, found.fixes)

        def inline(
            block: Sequence[Line],
            counts: Counter[str] = scratch,
            run_of: dict[int, int] = run_of,
            labels: _Labels = labels,
        ) -> list[Piece]:
            return assemble(
                labels.lines(block, Fixes()),
                ctx.vocabulary,
                Fixes(),
                counts,
                repair=ctx.repair,
                run_of=run_of,
                bold=True,
                split_fused=True,
            )

        flat = inline(intro.lines, found.fixes)
        spans = _spans(found, book.code, name, flat, runs, ctx)
        written = write(intro, inline, lambda pieces, spans=spans: relink(pieces, spans))
        for problem in written.problems:
            found.hygiene.setdefault(problem, []).append(name)
        checked = _QUERIED_DATE.sub("", written.plain)
        for pattern_name, pattern in HYGIENE.items():
            if pattern.search(checked):
                found.hygiene.setdefault(pattern_name, []).append(name)
        if broken_words(spaced(intro.lines, ctx), ctx.vocabulary):
            found.hygiene.setdefault("broken-word", []).append(name)
        if _WS_ALL.sub("", plain_text(flat)) != written.printed:
            found.errors.append(f"{name}: its blocks don't hold exactly the text it prints")
        assert intro.title_line is not None
        if written.title.casefold() != " ".join(intro.title_line.text.split()).casefold():
            found.errors.append(f"{name}: its title and its What's the Point name differ")
        found.documents.append(
            {
                "slug": slug(book.code),
                "kind": KIND,
                "title": written.title,
                "book": book.code,
                "ordinal": book.order,
                "text": written.markdown,
            }
        )
        found.assets[intro.figure.name] = intro.figure.data
        heads = [" ".join(h.text.split()) for h in intro.heads]
        found.heads.update(heads)
        found.head_lists[book.code] = heads
        counted = structures(intro)
        found.structures.update(counted)
        found.timelines += 1 if counted["timeline"] else 0
        found.words[book.code] = len(written.plain.split())
        figure_block = next(b for b in intro.blocks if b.kind is Kind.FIGURE)
        found.captions[book.code] = " ".join(figure_block.groups[0][0].text.split())
        parts = sections(intro.lines)
        found.section_heads[book.code] = [" ".join(part[0].text.split()) for part in parts]
        for n, part in enumerate(parts, 1):
            k = key(book.code, n)
            found.texts[k] = plain_text(inline(part))
            _texts(found, k, part, ctx, run_of, labels)
    found.head_order, out_of_order = head_order(found.head_lists)
    found.errors += [f"{book}: its heads are out of the common order" for book in out_of_order]
    return found


def head_order(head_lists: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """The heads' one order (each printed form placed after the head it first follows) and
    the books that print theirs out of it."""
    order: list[str] = []
    for heads in head_lists.values():
        previous = -1
        for head in heads:
            if head not in order:
                order.insert(previous + 1, head)
            previous = order.index(head)
    out_of_order = [
        book
        for book, heads in head_lists.items()
        if [order.index(h) for h in heads] != sorted(order.index(h) for h in heads)
    ]
    return order, out_of_order


def _spans(
    found: IntroductionFindings,
    book: str,
    name: str,
    flat: list[Piece],
    runs: list[LinkRun],
    ctx: Context,
) -> dict[int, list[tuple[int, int, str]]]:
    return link_spans(
        found.links,
        found.errors,
        book,
        name,
        flat,
        runs,
        (0, 0),
        ctx,
        reviewed=REVIEWED_INTRODUCTION_LINKS,
    )


def _texts(
    found: IntroductionFindings,
    k: Key,
    lines: list[Line],
    ctx: Context,
    run_of: dict[int, int],
    labels: _Labels,
) -> None:
    """Record an introduction's plain text with no fixes and with each fix alone."""
    none = Fixes.none()
    scratch: Counter[str] = Counter()

    def plain(fixes: Fixes) -> str:
        return plain_text(
            assemble(
                labels.lines(lines, fixes),
                ctx.vocabulary,
                fixes,
                scratch,
                repair=ctx.repair,
                run_of=run_of,
                bold=True,
                split_fused=True,
            )
        )

    found.raw[k] = plain(none)
    for fix in dataclasses.fields(Fixes):
        found.solo.setdefault(fix.name, {})[k] = plain(
            dataclasses.replace(none, **{fix.name: True})
        )
    pages = [line.page for line in lines]
    found.spans[k] = (min(pages), max(pages))


def documents_payload(found: IntroductionFindings, code: str) -> dict[str, object]:
    return {"translation": code, "documents": found.documents}


def word_sizes(found: IntroductionFindings) -> tuple[tuple[int, str], int, tuple[int, str]]:
    """(shortest, its book), the median, (longest, its book)."""
    ordered = sorted((n, book) for book, n in found.words.items())
    return ordered[0], int(statistics.median(n for n, _ in ordered)), ordered[-1]


# --- the EPUB witness --------------------------------------------------------------------------


@dataclass(slots=True)
class EpubIntroductions:
    texts: dict[Key, str] = field(default_factory=dict[Key, str])
    damaged: set[Key] = field(default_factory=set[Key])
    figures: dict[str, str] = field(default_factory=dict[str, str])  # book → FIGURE_WITNESS
    lost_heads: list[str] = field(default_factory=list[str])  # "BOOK §n": a head the EPUB lacks


# What the EPUB shows after an introduction's caption.
FIGURE_WITNESS = ("under its caption", "image markup damaged", "not found")
_IMAGE_SCRAP = re.compile(r"recindex=|alt=\"|\.jpg|height=\"\d|/>|^\"?>$")


def _figure_witness(blocks: list[str], caption: str) -> str:
    for n, block in enumerate(blocks):
        if not caption or caption not in " ".join(block.split()):
            continue
        after = blocks[n + 1] if n + 1 < len(blocks) else ""
        if after == IMAGE:
            return FIGURE_WITNESS[0]
        if _IMAGE_SCRAP.search(after):
            return FIGURE_WITNESS[1]
    return FIGURE_WITNESS[2]


def _navigation(tokens: list[str]) -> bool:
    """A row of the navigation list: chapter numbers (the first row opens with a word), maybe
    with a markup scrap."""
    rest = [t for t in tokens[1:] if "=" not in t and t != ">"]
    numbers = [t.lstrip(">") for t in rest]
    return (
        bool(tokens)
        and all(t.isdigit() for t in numbers)
        and (tokens[0].isdigit() or len(tokens) > 1)
    )


def epub_introductions(epub: EpubBible, found: IntroductionFindings) -> EpubIntroductions:
    """Each book's introduction as the EPUB has it, split into the PDF's sections: its text
    from the first section head on (the navigation list and the title before it dropped), cut
    at each section's opening line in order; a head the EPUB lost merges its section into the
    one before, both marked damaged. The callout labels the PDF sets aside and the ornament are
    dropped; whether an image follows the caption is noted."""
    out = EpubIntroductions()
    for book, blocks in epub.intros.items():
        heads = found.section_heads.get(book, [])
        caption = found.captions.get(book, "")
        texts = [b for b in blocks if b != IMAGE]
        out.figures[book] = _figure_witness(blocks, caption)
        leading = 0
        while leading < len(texts) and _navigation(texts[leading].split()):
            leading += 1
        text = " ".join(" ".join(texts[leading:]).split())
        for label in found.callout_labels.get(book, []):
            if text.endswith(label):
                text = text[: -len(label)].rstrip()
        text = " ".join(t for t in text.split(" ") if not _ORNAMENT.match(t))
        if not heads:
            continue
        found_at: list[int | None] = []
        at = 0
        for head in heads:
            position = text.find(head, at)
            found_at.append(position if position >= 0 else None)
            if position >= 0:
                at = position + len(head)
        starts = [p for p in found_at if p is not None]
        for n, position in enumerate(found_at, 1):
            k = key(book, n)
            later = [p for p in starts if position is not None and p > position]
            if position is not None:
                part = text[position : later[0] if later else len(text)]
            elif n == 1 and starts:  # the first head lost: what stands before the next one
                part = text[: starts[0]]
                out.damaged.add(k)
            else:
                part = ""
            if position is None:
                out.lost_heads.append(f"{book} §{n}")
                earlier = [m for m in range(1, n) if found_at[m - 1] is not None]
                if earlier:  # its text ran on into the section before
                    out.damaged.add(key(book, earlier[-1]))
            if BREAK in part:
                out.damaged.add(k)
                part = part.replace(BREAK, " ")
            out.texts[k] = " ".join(part.split())
    return out


def cross_check_epub_introductions(
    found: IntroductionFindings,
    epub: EpubBible,
    doc: PdfDocument,
    layout: Layout,
    verse_texts: dict[Key, str],
) -> tuple[CrossCheck, EpubIntroductions]:
    """The introductions' text, PDF vs EPUB, keyed by book, with the notes' classes and
    evidence rules."""
    witness = epub_introductions(epub, found)
    pages: dict[int, list[str]] = {}
    spans = set(range(layout.bible_start, layout.notes_start))
    for item in doc.items:
        if item.page in spans:
            pages.setdefault(item.page, []).append(item.text)
    cross = cross_check_notes(
        fixed=found.texts,
        raw=found.raw,
        solo=found.solo,
        epub=witness.texts,
        epub_damaged=witness.damaged,
        context_texts={**verse_texts, **found.texts},
        pages={page: " ".join(t) for page, t in pages.items()},
        spans=found.spans,
    )
    return cross, witness


def write_documents(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, "utf-8")
