"""The Bible-text pass: chapters, verses, headings, psalm titles and ``*`` markers.

Reads the lines of the Bible region in order and runs a small state machine over them. Every
rule is structural (font size, colour, bold/italic, link target, position, book/chapter
context); none matches the book's words. What a rule can't claim is counted as
*unclassified* and fails the run, so nothing reaches a verse by default.

Rules (docs/v8/SPEC.md §3, the S1 plan):

- Chapter: a blue size-23 numeral (after the blue size-15 book name). A single-chapter book
  opens at its first size-7 "1". A size-7 "N:" label before a verse number turns the chapter
  early (Dan 11:1); the header for N that follows is then a no-op.
- Verse number: size 7, ``\\d+`` or ``\\d+-\\d+`` (combined, stored under its first number).
- Heading: a line whose content is all bold+italic; wrapped lines join. Also Ps 119's stanza
  labels and Song of Songs' speaker labels (italic-only lines in those books).
- Italic-only lines elsewhere: a psalm title (before a psalm's first verse — prefixed to verse
  1), verse text inside a Psalms verse (Interlude, refrains), or verse text continuing an
  unfinished sentence (an italic book title wrapped onto its own line). Anything else is
  unclassified.
- Never verse text: book intros and chapter-navigation lists, Perspectives boxes (label →
  reference → attribution; recorded with where they stand, V8-S3b), callout labels (bold blue
  links into the feature region), table header rows.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from emb_convert.clean import (
    CompoundRepair,
    Fixes,
    PublicWords,
    Vocabulary,
    collapse,
    fraction,
    line_joiner,
    unspace,
)
from emb_convert.layout import BookRange, Layout, LinkKind
from emb_convert.lines import Line, group_lines
from emb_convert.pdfxml import ImageItem, PdfDocument, TextItem
from emb_convert.tables import CELL_SEPARATOR, Table, build_rows, find_tables

VERSE_NUMBER_SIZE = 7
BODY_SIZE = 12
BOOK_NAME_SIZE = 15
CHAPTER_NUMBER_SIZE = 23
BOX_LABEL_SIZE = 9
HEADING_WRAP = 18  # max points between two lines of one wrapped heading
WRAP_RIGHT = 330  # a body line reaching this x ran to the right margin (justified prose)
NEW_LINE_INDENT = 46  # a paragraph's or a poetic line's first line (wraps resume at 38/61)
MAX_BOX_LINES = 80

PSALMS = "PSA"
SONG = "SNG"
STANZA_PSALM = 119

_VERSE_NUMBER = re.compile(r"^(\d+)(?:-(\d+))?$")
_CHAPTER_LABEL = re.compile(r"^(\d+):$")
_LABEL_SPLIT = re.compile(r"^(\w+) ([a-z])$")
_TERMINAL = ".!?"
_CLOSERS = "”’\"' "


class ParseError(Exception):
    """The Bible text broke a structural rule the converter relies on."""


class Where(Enum):
    VERSE = "verse"
    TITLE = "title"
    HEADING = "heading"
    CHAPTER = "chapter"  # on the chapter header: anchored at the start of verse 1


@dataclass(slots=True)
class ParsedVerse:
    number: int
    last: int
    text: str
    pages: tuple[int, int] = (0, 0)  # first and last PDF page the verse's text sits on


@dataclass(slots=True)
class ParsedHeading:
    before_verse: int
    text: str


@dataclass(slots=True)
class ParsedChapter:
    number: int
    verses: list[ParsedVerse] = field(default_factory=list[ParsedVerse])
    headings: list[ParsedHeading] = field(default_factory=list[ParsedHeading])


@dataclass(slots=True)
class ParsedBook:
    code: str
    name: str
    order: int
    chapters: list[ParsedChapter] = field(default_factory=list[ParsedChapter])


@dataclass(frozen=True, slots=True)
class Marker:
    """A removed ``*``: where it sat, and the textual-note page it linked to."""

    book: str
    chapter: int
    verse: int
    offset: int
    where: Where
    target_page: int
    ordinal: int


@dataclass(frozen=True, slots=True)
class Callout:
    """A blue verse number: the book calls out a study note at this verse (V8-S2b)."""

    book: str
    chapter: int
    verse: int
    target_page: int


@dataclass(slots=True)
class FeatureCallout:
    """A callout line: the book points to a feature article here (V8-S3a).

    ``after`` is the verse open when the line comes — (chapter, verse), None in a book's
    introduction — and ``before`` the next verse to start; ``mid_verse`` says the open verse's
    text went on after the line."""

    book: str
    label: str
    target_page: int
    page: int
    after: tuple[int, int] | None
    before: tuple[str, int, int] | None = None  # (book, chapter, verse)
    in_intro: bool = False
    mid_verse: bool = False


@dataclass(slots=True)
class PerspectivesBox:
    """A Perspectives box: its lines (label first) and where it stands (V8-S3b).

    ``after`` is the verse open when the box opens — (chapter, verse) — and ``before`` the next
    verse to start; ``mid_verse`` says the open verse's text went on after the box;
    ``callouts_before`` is how many callout lines came before it (their reading order)."""

    book: str
    page: int
    after: tuple[int, int] | None
    callouts_before: int
    lines: list[Line] = field(default_factory=list[Line])
    before: tuple[str, int, int] | None = None
    mid_verse: bool = False


@dataclass(slots=True)
class ChartImage:
    """Where a chart's image stands in the text (V8-S4b).

    ``after`` is the verse open when the image comes — (chapter, verse) — and ``before`` the
    next verse to start; ``mid_verse`` says the open verse's text went on after the image."""

    book: str
    page: int
    top: int
    after: tuple[int, int] | None
    before: tuple[str, int, int] | None = None
    mid_verse: bool = False


@dataclass(slots=True)
class Diagnostics:
    counts: Counter[str] = field(default_factory=Counter[str])
    combined: list[str] = field(default_factory=list[str])
    mid_verse_headings: list[str] = field(default_factory=list[str])
    unclassified: list[str] = field(default_factory=list[str])
    tables: list[Table] = field(default_factory=list[Table])
    lone_wide_lines: list[str] = field(default_factory=list[str])
    nav_chapters: dict[str, int] = field(default_factory=dict[str, int])
    where: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    callout_labels: list[tuple[str, int, str]] = field(default_factory=list[tuple[str, int, str]])
    italic_verse_text: set[str] = field(default_factory=set[str])  # Interlude and kin
    callouts: list[Callout] = field(default_factory=list[Callout])  # study-note verse numbers
    feature_callouts: list[FeatureCallout] = field(default_factory=list[FeatureCallout])
    boxes: list[PerspectivesBox] = field(default_factory=list[PerspectivesBox])
    charts: list[ChartImage] = field(default_factory=list[ChartImage])
    # each book's introduction as printed: the lines read before its first chapter, after its
    # navigation page, callout lines aside (V8-S5b)
    intros: dict[str, list[Line]] = field(default_factory=dict[str, list[Line]])

    def note(self, kind: str, ref: str) -> None:
        self.counts[kind] += 1
        self.where.setdefault(kind, []).append(ref)

    errors: list[str] = field(default_factory=list[str])


@dataclass(slots=True)
class ParseResult:
    books: list[ParsedBook]
    markers: list[Marker]
    diagnostics: Diagnostics


# --- text buffers ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Break:
    wrapped: bool  # the line before ran to the right margin


@dataclass(slots=True)
class _Mark:
    target_page: int
    seq: int
    chapter: bool = False


_Piece = str | _Mark | _Break


@dataclass(slots=True)
class _Buffer:
    pieces: list[_Piece] = field(default_factory=list[_Piece])

    def add(self, text: str) -> None:
        self.pieces.append(text)

    def mark(self, mark: _Mark) -> None:
        self.pieces.append(mark)

    def line_break(self, *, wrapped: bool = False) -> None:
        if self.pieces and not isinstance(self.pieces[-1], _Break):
            self.pieces.append(_Break(wrapped))

    def empty(self) -> bool:
        return not any(isinstance(p, str) and p.strip() for p in self.pieces)

    def ends_sentence(self) -> bool:
        text = "".join(p for p in self.pieces if isinstance(p, str)).rstrip(_CLOSERS)
        return text[-1:] in _TERMINAL


def assemble(
    buffer: _Buffer, fixes: Fixes, repair: CompoundRepair | None, counts: Counter[str]
) -> tuple[str, list[tuple[int, _Mark]]]:
    """Join a buffer's pieces into clean text; return it with each marker's offset."""
    out = ""
    marks: list[tuple[int, _Mark]] = []
    pending_break: _Break | None = None
    for piece in buffer.pieces:
        if isinstance(piece, _Break):
            pending_break = piece
        elif isinstance(piece, _Mark):
            marks.append((len(out.rstrip()), piece))
        else:
            text = collapse(piece)
            if repair is not None and fixes.compound_hyphens:
                text, repaired = repair.repair(text)
                counts["compound-hyphens"] += repaired
            if pending_break is not None and out.strip() and text.strip():
                tail = out.rstrip()
                joiner = line_joiner(tail, text, fixes, wrapped=pending_break.wrapped)
                out = tail + joiner + text.lstrip()
            elif pending_break is not None:
                out += " " + text
            else:
                out += text
            pending_break = None
            out = re.sub(r" {2,}", " ", out)
    lead = len(out) - len(out.lstrip())
    text = out.strip()
    return text, [(min(max(offset - lead, 0), len(text)), mark) for offset, mark in marks]


# --- the parser ------------------------------------------------------------------------


@dataclass(slots=True)
class _HeadingDraft:
    buffer: _Buffer
    last_page: int
    last_top: int
    label: bool = False
    last_right: int = 0


class _Mode(Enum):
    INTRO = "intro"
    TEXT = "text"
    BOX = "box"


@dataclass(slots=True)
class _Box:
    references: int = 0
    attributions: int = 0
    lines: int = 0
    where: str = ""


def trusted_text(line: Line) -> list[str]:
    """A line's text minus where broken words occur (the vocabulary's PDF source): the first
    item's leading single-spaced chunk, and italic items."""
    texts: list[str] = []
    content = line.nonblank
    for item in content:
        if item.italic:
            continue
        if item is content[0]:
            cut = item.text.strip().find("  ")
            if cut != -1:
                texts.append(item.text.strip()[cut:])
            continue
        texts.append(item.text)
    return texts


class _Parser:
    def __init__(
        self,
        doc: PdfDocument,
        layout: Layout,
        fixes: Fixes,
        public: PublicWords,
        charts: Sequence[ImageItem] = (),
    ) -> None:
        self.layout = layout
        self.fixes = fixes
        items = [i for i in doc.items if layout.bible_start <= i.page < layout.notes_start]
        self.lines = group_lines(items)
        self.repair = CompoundRepair(line.text for line in self.lines)
        self.vocabulary = Vocabulary(
            public, (text for line in self.lines for text in trusted_text(line))
        )
        self.diag = Diagnostics()
        self.books: list[ParsedBook] = []
        self.book: ParsedBook | None = None
        self.book_range: BookRange | None = None
        self.chapter: ParsedChapter | None = None
        self.mode = _Mode.INTRO
        self.verse: tuple[int, int] | None = None
        self.verse_pages: tuple[int, int] = (0, 0)
        self.verse_buffer = _Buffer()
        self.verse_title: _Buffer | None = None
        self.title = _Buffer()
        self.title_right = 0
        self.pending: list[_HeadingDraft] = []
        self.intro_headings: list[_HeadingDraft] = []
        self.chapter_label: int | None = None
        self.chapter_marks: list[_Mark] = []
        self.after_header: tuple[int, int] | None = None
        self.wrapped = False  # did the last body line run to the right margin?
        self.box = _Box()
        self.seq = 0
        self.pending_callouts: list[FeatureCallout] = []
        self.pending_boxes: list[PerspectivesBox] = []
        self.chart_queue = sorted(charts, key=lambda c: (c.page, c.top), reverse=True)
        self.pending_charts: list[ChartImage] = []
        self.raw_marks: list[tuple[str, int, int, Where, int, _Mark]] = []
        self.heading_marks: list[tuple[str, int, ParsedHeading, int, _Mark]] = []
        scan = find_tables(self.lines)
        self.tables = {table.first: table for table in scan.tables}
        self.diag.tables = scan.tables
        for index in scan.lone_wide_lines:
            line = self.lines[index]
            self.diag.lone_wide_lines.append(f"p{line.page} top {line.top}")

    # -- small predicates

    def link_kind(self, item: TextItem) -> LinkKind | None:
        return self.layout.link_kind(item.link_page) if item.link_page is not None else None

    def is_marker(self, item: TextItem) -> bool:
        return item.stripped == "*" and item.blue and self.link_kind(item) is LinkKind.TEXTUAL_NOTE

    @staticmethod
    def is_verse_number(item: TextItem) -> bool:
        return item.size == VERSE_NUMBER_SIZE and bool(_VERSE_NUMBER.match(item.stripped))

    def where(self, line: Line) -> str:
        book = self.book.code if self.book else "?"
        chapter = self.chapter.number if self.chapter else 0
        verse = self.verse[0] if self.verse else 0
        return f"{book} {chapter}:{verse} (p{line.page} top {line.top})"

    def ref(self) -> str:
        book = self.book.code if self.book else "?"
        chapter = self.chapter.number if self.chapter else 0
        verse = self.verse[0] if self.verse else 0
        return f"{book} {chapter}:{verse}"

    # -- driving

    def run(self) -> ParseResult:
        index = 0
        while index < len(self.lines):
            line = self.lines[index]
            self.charts_before((line.page, line.top))
            table = self.tables.get(index)
            if table is not None and self.mode is _Mode.TEXT and self.chapter is not None:
                self.table(table)
                index = table.last + 1
                continue
            self.line(line)
            index += 1
        self.charts_before(None)
        self.end_book()
        if self.mode is _Mode.BOX:
            self.diag.errors.append(f"unterminated Perspectives box at {self.box.where}")
        return ParseResult(self.books, self.markers(), self.diag)

    def line(self, line: Line) -> None:
        content = line.nonblank
        if not content:
            return
        wrapped, self.wrapped = self.wrapped, False
        self.wrapped = wrapped if self.continues_body(line) else False
        book_range = self.layout.book_at(line.page)
        if book_range is None:
            raise ParseError(f"p{line.page} is outside every book")
        if self.book_range is None or book_range.code != self.book_range.code:
            self.start_book(book_range)
        if self.mode is _Mode.BOX and self.box_line(content):
            self.diag.boxes[-1].lines.append(line)
            return
        after_header = self.after_header == (line.page, self.chapter_index())
        self.after_header = None
        words = [i for i in content if not self.is_marker(i)]
        if any(self.is_chapter_number(i) for i in content):
            self.chapter_header(line, content)
            self.after_header = (line.page, self.chapter_index())
            return
        if (words and all(self.is_book_name(i) for i in words)) or (not words and after_header):
            # a chapter header's book name or its "*", set a few points off its numeral
            self.header_marks(content)
            self.after_header = (line.page, self.chapter_index())
            return
        if self.mode is _Mode.INTRO and self.is_callout_line(content):
            self.feature_callout(line, content, in_intro=True)  # one in a book's introduction
            self.diag.counts["callout-lines-in-intros"] += 1
            return
        if self.mode is _Mode.INTRO and not self.intro_line(line, content):
            assert self.book_range is not None
            if line.page > self.book_range.start_page:  # past the navigation page
                self.diag.intros.setdefault(self.book_range.code, []).append(line)
            return
        if any(
            i.size == BOX_LABEL_SIZE and i.blue and self.link_kind(i) is LinkKind.FEATURE
            for i in content
        ):
            self.mode = _Mode.BOX
            self.box = _Box(where=self.where(line))
            self.diag.counts["perspectives-boxes"] += 1
            self.perspectives_box(line)
            return
        if self.is_callout_line(content):
            self.diag.counts["callout-lines"] += 1
            if self.book is not None and self.chapter is not None:
                label = collapse(line.text).strip()
                self.diag.callout_labels.append((self.book.code, self.chapter.number, label))
            self.feature_callout(line, content, in_intro=False)
            return
        words = [i for i in content if not self.is_marker(i)]
        if words and all(i.bold and i.italic for i in words):
            self.heading_line(line, label=False)
        elif words and all(i.italic and not i.bold for i in words):
            self.italic_line(line)
        else:
            self.text_line(line)

    def is_callout_line(self, content: list[TextItem]) -> bool:
        return all(i.blue and i.bold and self.link_kind(i) is LinkKind.FEATURE for i in content)

    def feature_callout(self, line: Line, content: list[TextItem], *, in_intro: bool) -> None:
        """Record where a callout line stands; ``start_verse`` fills in the verse after it."""
        assert self.book_range is not None
        after = None
        if not in_intro and self.chapter is not None and self.verse is not None:
            after = (self.chapter.number, self.verse[0])
        callout = FeatureCallout(
            book=self.book_range.code,
            label=collapse(line.text).strip(),
            target_page=content[0].link_page or 0,
            page=line.page,
            after=after,
            in_intro=in_intro,
        )
        self.diag.feature_callouts.append(callout)
        self.pending_callouts.append(callout)

    def charts_before(self, where: tuple[int, int] | None) -> None:
        """Record every chart image placed before ``where`` (page, top) — all when None."""
        while self.chart_queue and (
            where is None or (self.chart_queue[-1].page, self.chart_queue[-1].top) < where
        ):
            self.chart_image(self.chart_queue.pop())

    def chart_image(self, image: ImageItem) -> None:
        """Record where a chart stands; ``start_verse`` fills in the verse after it."""
        book_range = self.layout.book_at(image.page)
        if book_range is None or self.book_range is None or book_range != self.book_range:
            self.diag.errors.append(f"the chart on p{image.page} stands outside its book's text")
            return
        if self.mode is not _Mode.TEXT:
            self.diag.errors.append(f"the chart on p{image.page} stands in a {self.mode.value}")
            return
        after = None
        if self.chapter is not None and self.verse is not None:
            after = (self.chapter.number, self.verse[0])
        chart = ChartImage(book=book_range.code, page=image.page, top=image.top, after=after)
        self.diag.charts.append(chart)
        self.pending_charts.append(chart)

    def perspectives_box(self, line: Line) -> None:
        """Record where a box stands; ``start_verse`` fills in the verse after it."""
        assert self.book_range is not None
        after = None
        if self.chapter is not None and self.verse is not None:
            after = (self.chapter.number, self.verse[0])
        box = PerspectivesBox(
            book=self.book_range.code,
            page=line.page,
            after=after,
            callouts_before=len(self.diag.feature_callouts),
            lines=[line],
        )
        self.diag.boxes.append(box)
        self.pending_boxes.append(box)

    def chapter_index(self) -> int:
        return self.chapter.number if self.chapter else 0

    def is_book_name(self, item: TextItem) -> bool:
        assert self.book_range is not None
        return (
            item.size == BOOK_NAME_SIZE
            and item.blue
            and item.link_page == self.book_range.start_page
        )

    def continues_body(self, line: Line) -> bool:
        """Whether ``line`` can continue a wrapped body line (anything but a non-body line)."""
        words = [i for i in line.nonblank if not self.is_marker(i)]
        return bool(words) and not all(i.italic for i in words)

    @staticmethod
    def is_chapter_number(item: TextItem) -> bool:
        return item.size == CHAPTER_NUMBER_SIZE and item.blue and item.stripped.isdigit()

    # -- books and chapters

    def start_book(self, book_range: BookRange) -> None:
        self.end_book()
        self.book_range = book_range
        self.book = ParsedBook(code=book_range.code, name=book_range.name, order=book_range.order)
        self.books.append(self.book)
        self.chapter = None
        self.mode = _Mode.INTRO
        self.intro_headings = []
        self.pending = []
        self.chapter_label = None

    def end_book(self) -> None:
        self.flush_verse()
        if self.pending and self.book is not None:
            self.diag.errors.append(f"{self.book.code}: headings left with no verse to attach")
        self.pending = []

    def new_chapter(self, number: int, line: Line) -> None:
        assert self.book is not None
        self.flush_verse()
        expected = self.chapter.number + 1 if self.chapter else 1
        if number != expected:
            self.diag.errors.append(
                f"chapter {number} where {expected} was expected at {line.page}"
            )
        self.chapter = ParsedChapter(number=number)
        self.book.chapters.append(self.chapter)
        self.verse = None
        self.title = _Buffer()
        self.title_right = 0

    def chapter_header(self, line: Line, content: list[TextItem]) -> None:
        if self.mode is _Mode.BOX:
            self.diag.errors.append(f"chapter header inside a Perspectives box at {self.box.where}")
        number = int(next(i for i in content if self.is_chapter_number(i)).stripped)
        self.header_marks(content)
        assert self.book_range is not None
        if any(i.link_page != self.book_range.start_page for i in content if i.blue):
            self.diag.errors.append(
                f"chapter header {number} links outside its book at {line.page}"
            )
        if self.mode is _Mode.INTRO:
            self.pending.extend(d for d in self.intro_headings if d.last_page == line.page)
            self.intro_headings = []
        self.mode = _Mode.TEXT
        if self.chapter is not None and self.chapter.number == number:
            self.diag.counts["chapter-headers-after-label"] += 1
            return
        self.new_chapter(number, line)
        self.diag.counts["chapter-headers"] += 1

    def header_marks(self, content: list[TextItem]) -> None:
        """A ``*`` on a chapter header notes the whole chapter (an acrostic psalm)."""
        for item in content:
            if self.is_marker(item):
                self.seq += 1
                self.chapter_marks.append(
                    _Mark(target_page=item.link_page or 0, seq=self.seq, chapter=True)
                )

    def intro_line(self, line: Line, content: list[TextItem]) -> bool:
        """Handle a line before the book's first chapter; True when text starts here."""
        assert self.book_range is not None and self.book is not None
        if line.page == self.book_range.start_page:
            for item in content:
                if item.blue and item.stripped.isdigit() and item.size == BODY_SIZE:
                    current = self.diag.nav_chapters.get(self.book.code, 0)
                    self.diag.nav_chapters[self.book.code] = max(current, int(item.stripped))
        single = self.book_range.code in _SINGLE_CHAPTER
        first = content[0]
        if single and self.is_verse_number(first) and first.stripped == "1":
            self.pending.extend(d for d in self.intro_headings if d.last_page == line.page)
            self.intro_headings = []
            self.mode = _Mode.TEXT
            self.new_chapter(1, line)
            return True
        if all(i.bold and i.italic for i in content):
            # a heading above the first chapter ("Book One" over Psalm 1): kept only when it
            # sits on the page where the chapter (or single-chapter text) starts
            draft = self.intro_headings[-1] if self.intro_headings else None
            if (
                draft is not None
                and draft.last_page == line.page
                and (line.top - draft.last_top <= HEADING_WRAP)
            ):
                self.extend_heading(draft, line)
            else:
                self.intro_headings.append(self.new_heading(line, label=False))
        return False

    # -- verses

    def start_verse(self, first: int, last: int) -> None:
        assert self.chapter is not None and self.book is not None
        for callout in self.pending_callouts:
            callout.before = (self.book.code, self.chapter.number, first)
        self.pending_callouts = []
        for box in self.pending_boxes:
            box.before = (self.book.code, self.chapter.number, first)
        self.pending_boxes = []
        for chart in self.pending_charts:
            chart.before = (self.book.code, self.chapter.number, first)
        self.pending_charts = []
        self.flush_verse()
        self.verse = (first, last)
        self.verse_pages = (0, 0)
        self.verse_buffer = _Buffer()
        if first == 1 and self.book.code == PSALMS and not self.title.empty():
            self.verse_title = self.title
        else:
            self.verse_title = None
        self.title = _Buffer()
        if last != first:
            self.diag.combined.append(f"{self.book.code} {self.chapter.number}:{first}-{last}")
        for draft in self.pending:
            self.attach(draft, first)
        self.pending = []
        for mark in self.chapter_marks:
            self.verse_buffer.mark(mark)
        self.chapter_marks = []

    def callout(self, item: TextItem, verse: int) -> None:
        """A blue verse number links to its study note: record where the book calls it out."""
        if (
            item.blue
            and item.link_page is not None
            and self.book is not None
            and self.chapter is not None
            and self.link_kind(item) is LinkKind.STUDY_NOTE
        ):
            self.diag.callouts.append(
                Callout(self.book.code, self.chapter.number, verse, item.link_page)
            )

    def flush_verse(self) -> None:
        if self.verse is None or self.chapter is None or self.book is None:
            return
        first, last = self.verse
        text, marks = assemble(self.verse_buffer, self.fixes, self.repair, self.diag.counts)
        code, chapter = self.book.code, self.chapter.number
        if self.verse_title is not None:
            title, title_marks = assemble(
                self.verse_title, self.fixes, self.repair, self.diag.counts
            )
            for offset, mark in title_marks:
                self.raw_marks.append((code, chapter, first, Where.TITLE, offset, mark))
            shift = len(title) + 1
            text = f"{title} {text}"
            self.diag.counts["psalm-titles"] += 1
            marks = [(offset + shift, mark) for offset, mark in marks]
        for offset, mark in marks:
            if mark.chapter:
                self.raw_marks.append((code, chapter, first, Where.CHAPTER, 0, mark))
            else:
                self.raw_marks.append((code, chapter, first, Where.VERSE, offset, mark))
        if not text:
            self.diag.errors.append(f"{code} {chapter}:{first} has no text")
        self.chapter.verses.append(
            ParsedVerse(number=first, last=last, text=text, pages=self.verse_pages)
        )
        self.verse = None
        self.verse_title = None

    # -- headings

    def new_heading(self, line: Line, *, label: bool) -> _HeadingDraft:
        draft = _HeadingDraft(
            buffer=_Buffer(),
            last_page=line.page,
            last_top=line.top,
            label=label,
            last_right=line.right,
        )
        self.fill(draft.buffer, line)
        return draft

    def extend_heading(self, draft: _HeadingDraft, line: Line) -> None:
        draft.buffer.line_break(wrapped=draft.last_right >= WRAP_RIGHT)
        self.fill(draft.buffer, line)
        draft.last_page, draft.last_top, draft.last_right = line.page, line.top, line.right

    def heading_line(self, line: Line, *, label: bool) -> None:
        draft = self.pending[-1] if self.pending else None
        if (
            draft is not None
            and not label
            and not draft.label
            and draft.last_page == line.page
            and line.top - draft.last_top <= HEADING_WRAP
        ):
            self.extend_heading(draft, line)
            return
        self.pending.append(self.new_heading(line, label=label))

    def attach(self, draft: _HeadingDraft, before_verse: int) -> None:
        assert self.chapter is not None and self.book is not None
        text, marks = assemble(draft.buffer, self.fixes, self.repair, self.diag.counts)
        if draft.label:
            joined = _LABEL_SPLIT.sub(r"\1\2", text)
            if joined != text:
                self.diag.note(
                    "label-joins", f"{self.book.code} {self.chapter.number}:{before_verse}"
                )
                text = joined
        heading = ParsedHeading(before_verse=before_verse, text=text)
        self.chapter.headings.append(heading)
        self.diag.counts["headings"] += 1
        for offset, mark in marks:
            self.heading_marks.append((self.book.code, self.chapter.number, heading, offset, mark))

    def attach_mid_verse(self) -> None:
        """Body text after a heading inside an open verse: the heading interrupts it."""
        if not self.pending or self.verse is None or self.chapter is None or self.book is None:
            return
        for draft in self.pending:
            self.attach(draft, self.verse[0])
            self.diag.mid_verse_headings.append(self.ref())
        self.pending = []

    # -- italic-only lines

    def italic_line(self, line: Line) -> None:
        assert self.book is not None and self.chapter is not None
        code, chapter = self.book.code, self.chapter.number
        if code == PSALMS and chapter == STANZA_PSALM:
            self.diag.counts["italic:stanza-label"] += 1
            self.heading_line(line, label=True)
        elif code == SONG:
            self.diag.counts["italic:speaker-label"] += 1
            self.heading_line(line, label=True)
        elif code == PSALMS and self.verse is None and not self.chapter.verses:
            self.diag.counts["italic:psalm-title"] += 1
            self.title.line_break(wrapped=self.title_right >= WRAP_RIGHT)
            self.fill(self.title, line)
            self.title_right = line.right
        elif code == PSALMS and self.verse is not None:
            self.diag.counts["italic:psalm-verse-text"] += 1
            self.diag.italic_verse_text.add(collapse(line.text).strip().rstrip("*").strip())
            self.body(line)
        elif self.verse is not None and not self.verse_buffer.ends_sentence():
            self.diag.note("italic:sentence-continuation", self.where(line))
            self.body(line)
        else:
            self.diag.counts["italic:unclaimed"] += 1
            self.diag.unclassified.append(f"italic-only line at {self.where(line)}")

    # -- body text

    def text_line(self, line: Line) -> None:
        self.body(line)

    def body(self, line: Line) -> None:
        """Feed a line's items into the current verse (or start verses on the way).

        The break before this line is a mere wrap when the last line ran to the right margin
        and this one doesn't open a new paragraph or poetic line (those start indented).
        """
        starts_new_line = min(i.left for i in line.nonblank) == NEW_LINE_INDENT
        self.verse_buffer.line_break(wrapped=self.wrapped and not starts_new_line)
        self.wrapped = line.right >= WRAP_RIGHT
        items = line.items
        first_content = next((i for i in items if i.stripped), None)
        i = 0
        while i < len(items):
            item = items[i]
            text = item.stripped
            nxt = items[i + 1] if i + 1 < len(items) else None
            if item.size == VERSE_NUMBER_SIZE and _CHAPTER_LABEL.match(text):
                self.chapter_label = int(text[:-1])
                i += 1
                continue
            if (
                item.size == VERSE_NUMBER_SIZE
                and text.isdigit()
                and nxt is not None
                and nxt.size == VERSE_NUMBER_SIZE
                and nxt.stripped == "/"
            ):
                den = items[i + 2].stripped if i + 2 < len(items) else ""
                self.verse_text(fraction(text, den, fixed=self.fixes.fractions), line)
                self.diag.counts["fractions"] += 1
                i += 3
                continue
            if self.is_verse_number(item):
                match = _VERSE_NUMBER.match(text)
                assert match is not None
                first = int(match.group(1))
                last = int(match.group(2) or first)
                if self.chapter_label is not None:
                    if self.chapter is None or self.chapter_label != self.chapter.number:
                        self.new_chapter(self.chapter_label, line)
                        self.diag.counts["chapter-labels"] += 1
                    self.chapter_label = None
                if self.chapter is None:
                    self.diag.unclassified.append(f"verse number before any chapter at {line.page}")
                else:
                    self.start_verse(first, last)
                    self.callout(item, first)
                i += 1
                continue
            if self.is_marker(item):
                if self.verse is None:
                    self.diag.unclassified.append(f"marker outside a verse at {self.where(line)}")
                else:
                    self.seq += 1
                    self.verse_buffer.mark(_Mark(target_page=item.link_page or 0, seq=self.seq))
                i += 1
                continue
            if text and not self.claims_as_text(item):
                self.diag.unclassified.append(
                    f"size-{item.size}{' blue' if item.blue else ''}"
                    f"{' bold' if item.bold else ''} item at {self.where(line)}"
                )
                i += 1
                continue
            glued = nxt is not None and self.is_small_caps(nxt)
            self.verse_text(self.unspaced(item, item is first_content, line, glued), line)
            i += 1

    @staticmethod
    def is_small_caps(item: TextItem) -> bool:
        text = item.stripped
        return (
            item.size == VERSE_NUMBER_SIZE
            and not item.blue
            and any(c.isalpha() for c in text)
            and text == text.upper()
            and not item.text[:1].isspace()
        )

    def claims_as_text(self, item: TextItem) -> bool:
        if item.bold and not item.italic:
            return False
        if item.size == BODY_SIZE:
            return not (item.blue and item.bold)
        # small caps ("L" + "ORD", "H" + "OLY TO THE") are size-7 capitals in the text
        text = item.stripped
        return (
            item.size == VERSE_NUMBER_SIZE
            and not item.blue
            and any(c.isalpha() for c in text)
            and not any(c.isdigit() for c in text)
            and text == text.upper()
        )

    def unspaced(self, item: TextItem, first: bool, line: Line, glued: bool = False) -> str:
        """``item``'s text with broken words joined (``clean.unspace``)."""
        if not self.fixes.letter_spacing:
            return item.text
        fixed = unspace(
            item.text,
            self.vocabulary,
            italic=item.italic,
            first=first,
            justified=line.right >= WRAP_RIGHT,
            glued=glued,
        )
        if fixed is None:
            return item.text
        self.diag.note("letter-spaced", self.where(line))
        return fixed

    def verse_text(self, text: str, line: Line) -> None:
        if not text.strip():
            if self.verse is not None:
                self.verse_buffer.add(text)
            return
        if self.verse is None:
            self.diag.unclassified.append(f"text outside a verse at {self.where(line)}")
            return
        self.attach_mid_verse()
        for callout in self.pending_callouts:
            callout.mid_verse = True  # the verse the line interrupts goes on
        for box in self.pending_boxes:
            box.mid_verse = True
        for chart in self.pending_charts:
            chart.mid_verse = True
        self.verse_buffer.add(text)
        start = self.verse_pages[0] or line.page
        self.verse_pages = (start, line.page)

    def fill(self, buffer: _Buffer, line: Line) -> None:
        """Copy a heading's or title's items into ``buffer``, recording ``*`` markers."""
        first = next((i for i in line.items if i.stripped), None)
        for n, item in enumerate(line.items):
            if self.is_marker(item):
                self.seq += 1
                buffer.mark(_Mark(target_page=item.link_page or 0, seq=self.seq))
            else:
                nxt = line.items[n + 1] if n + 1 < len(line.items) else None
                glued = nxt is not None and self.is_small_caps(nxt)
                buffer.add(self.unspaced(item, item is first, line, glued))

    # -- boxes

    def box_line(self, content: list[TextItem]) -> bool:
        """True while ``content`` belongs to the open Perspectives box."""
        attribution = all(i.size == VERSE_NUMBER_SIZE and not i.blue for i in content) and any(
            c.isalpha() for i in content for c in i.text
        )
        if self.box.attributions and not attribution:
            self.end_box()
            return False
        reference = any(
            i.size == VERSE_NUMBER_SIZE and i.blue and self.link_kind(i) is LinkKind.BIBLE
            for i in content
        )
        if reference:
            self.box.references += 1
        elif attribution and self.box.references:
            self.box.attributions += 1
        self.box.lines += 1
        if self.box.lines > MAX_BOX_LINES:
            self.diag.errors.append(f"Perspectives box never ends: {self.box.where}")
            self.end_box()
        return True

    def end_box(self) -> None:
        if self.box.references != 1:
            self.diag.errors.append(
                f"Perspectives box at {self.box.where} has {self.box.references} references"
            )
        self.mode = _Mode.TEXT

    # -- tables

    def table(self, table: Table) -> None:
        assert self.book is not None and self.chapter is not None
        first_ref: str | None = None
        rows = build_rows(
            table,
            self.lines,
            self.is_verse_number,
            fix_split_rows=self.fixes.table_split_rows,
        )
        for row in rows:
            self.verse_buffer.line_break()
            for item in row.lead:
                match = _VERSE_NUMBER.match(item.stripped)
                assert match is not None
                first = int(match.group(1))
                self.start_verse(first, int(match.group(2) or first))
                self.callout(item, first)
            if first_ref is None:
                first_ref = self.ref()
            for n, column in enumerate(sorted(row.cells)):
                if n:
                    self.verse_buffer.add(CELL_SEPARATOR)
                for k, cell_line in enumerate(row.cells[column]):
                    if k:
                        self.verse_buffer.line_break()
                    for item in cell_line:
                        if self.is_marker(item):
                            self.seq += 1
                            self.verse_buffer.mark(
                                _Mark(target_page=item.link_page or 0, seq=self.seq)
                            )
                        else:
                            self.verse_text(item.text, self.lines[table.first])
        table.where = f"{first_ref}–{self.ref().split(' ', 1)[1]}"
        self.diag.counts["table-rows"] += len(rows)

    # -- markers

    def markers(self) -> list[Marker]:
        found: list[tuple[int, Marker]] = []
        for code, chapter, verse, where, offset, mark in self.raw_marks:
            found.append(
                (mark.seq, Marker(code, chapter, verse, offset, where, mark.target_page, 0))
            )
        for code, chapter, heading, offset, mark in self.heading_marks:
            found.append(
                (
                    mark.seq,
                    Marker(
                        code,
                        chapter,
                        heading.before_verse,
                        offset,
                        Where.HEADING,
                        mark.target_page,
                        0,
                    ),
                )
            )
        found.sort(key=lambda pair: pair[0])
        ordinals: Counter[tuple[str, int]] = Counter()
        result: list[Marker] = []
        for _, marker in found:
            ordinals[(marker.book, marker.chapter)] += 1
            result.append(
                Marker(
                    marker.book,
                    marker.chapter,
                    marker.verse,
                    marker.offset,
                    marker.where,
                    marker.target_page,
                    ordinals[(marker.book, marker.chapter)],
                )
            )
        return result


_SINGLE_CHAPTER = frozenset({"OBA", "PHM", "2JN", "3JN", "JUD"})


def parse_bible(
    doc: PdfDocument,
    layout: Layout,
    fixes: Fixes | None = None,
    public: PublicWords | None = None,
    charts: Sequence[ImageItem] = (),
) -> ParseResult:
    """Parse the Bible text region of ``doc``.

    ``public`` (the committed public-domain translations as a word list) widens the words
    the letter-spacing fix checks against; the PDF's own words are always in it. ``charts``
    are the chart images (V8-S4b): each is recorded where it stands, and nothing else changes.
    """
    return _Parser(doc, layout, fixes or Fixes(), public or PublicWords(()), charts).run()
