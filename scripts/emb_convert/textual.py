"""The textual notes: the NLT footnotes behind each ``*`` (V8-S2b, docs/v8/SPEC.md §4.2).

The region between the Bible text and the feature indexes holds one block per chapter with
notes: a size-23 "<Book> <N> Textual Notes" header (sometimes wrapped onto a second line),
then each note, opened by a blue bold label that links back to the verse's page. Label
forms, as measured on the PDF:

- ``C:V`` — a verse; ``C:Va`` … ``C:Ve`` — one of several notes on a verse (an a/b split);
- ``C:V-V`` (a letter allowed at either end) — a range; its ``*`` sits in the last verse;
- ``C:`` + small-caps ``TITLE`` — a psalm title;
- a bare number — the chapter (the ``*`` on an acrostic psalm's header), or, in the five
  single-chapter books, a verse (``V``, ``Va``, ``V-V``).

Notes pair with S1's markers (``text.Marker``) chapter by chapter, in reading order: a note
*accepts* a marker of its own kind at a verse its label covers. Whatever doesn't pair is
listed — a marker without a note, a note without a marker — and fails the run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from bible_core.normalize import normalize

from emb_convert.layout import Layout
from emb_convert.lines import Line, group_lines
from emb_convert.pdfxml import PdfDocument, TextItem
from emb_convert.text import Marker, Where

HEADER_SIZE = 23
LABEL_SIZE = 12
TITLE_WORD = "TITLE"
HEADER_SUFFIX = "Textual Notes"
SINGLE_CHAPTER = frozenset({"OBA", "PHM", "2JN", "3JN", "JUD"})

_HEADER = re.compile(r"^(.+?) (\d+) Textual Notes$")
_LABEL = re.compile(r"^(?:(\d+):)?(\d+)([a-e])?(?:-(?:(\d+):)?(\d+)([a-e])?)?$")
_TITLE_LABEL = re.compile(r"^(\d+):$")

Key = tuple[str, int, int]


class LabelKind(Enum):
    """The label's printed form. The kinds don't overlap; together they count every note."""

    VERSE = "C:V"
    LETTERED = "C:V + letter"
    RANGE = "range"
    TITLE = "psalm title"
    CHAPTER = "chapter header"
    SINGLE = "single-chapter book"


@dataclass(frozen=True, slots=True)
class Label:
    text: str  # as printed: "1:26a", "6:TITLE", "25"
    kind: LabelKind
    first: int  # first verse covered (1 for a title or chapter note)
    last: int
    letter: str  # "a"…"e", or ""
    lettered_verse: int  # the verse the letter belongs to


@dataclass(slots=True)
class TextualNote:
    book: str
    chapter: int
    label: Label
    page: int
    items: list[TextItem]  # the label's own items first
    label_items: int

    @property
    def ref(self) -> str:
        """The note by its label: "GEN 1:26a", "PSA 6:TITLE", "PSA 25", "JUD 9"."""
        return f"{self.book} {self.label.text}"

    @property
    def lines(self) -> list[Line]:
        return group_lines(self.items)

    @property
    def label_ids(self) -> frozenset[int]:
        return frozenset(id(i) for i in self.items[: self.label_items])


@dataclass(slots=True)
class TextualRegion:
    notes: list[TextualNote] = field(default_factory=list[TextualNote])
    blocks: int = 0
    errors: list[str] = field(default_factory=list[str])


def parse_label(text: str, book: str, chapter: int, *, title: bool) -> Label | str:
    """A note's label, or an error message."""
    if title:
        match = _TITLE_LABEL.match(text)
        if match is None or int(match.group(1)) != chapter:
            return f"{book} {chapter}: title label {text!r}"
        return Label(f"{text}{TITLE_WORD}", LabelKind.TITLE, 1, 1, "", 1)
    match = _LABEL.match(text)
    if match is None:
        return f"{book} {chapter}: label {text!r}"
    c1, v1, l1, c2, v2, l2 = match.groups()
    if (c1 is not None and int(c1) != chapter) or (c2 is not None and int(c2) != chapter):
        return f"{book} {chapter}: label {text!r} names another chapter"
    first, last = int(v1), int(v2 or v1)
    letter = l1 or l2 or ""
    lettered = first if l1 else last
    if c1 is None and book not in SINGLE_CHAPTER:
        if v2 is None and not letter and first == chapter:
            return Label(text, LabelKind.CHAPTER, 1, 1, "", 1)
        return f"{book} {chapter}: bare label {text!r} outside a single-chapter book"
    if last < first:
        return f"{book} {chapter}: label {text!r} ends before it starts"
    if c1 is None:
        kind = LabelKind.SINGLE
    elif v2 is not None:
        kind = LabelKind.RANGE
    elif letter:
        kind = LabelKind.LETTERED
    else:
        kind = LabelKind.VERSE
    return Label(text, kind, first, last, letter, lettered)


def parse_textual(doc: PdfDocument, layout: Layout, by_alias: dict[str, str]) -> TextualRegion:
    """Every textual note, in book order, with its label and items."""
    region = TextualRegion()
    items = [i for i in doc.items if layout.notes_start <= i.page < layout.features_start]
    header: list[str] = []
    block: tuple[str, int] | None = None
    k = 0
    while k < len(items):
        item = items[k]
        if item.size == HEADER_SIZE:
            header.append(item.stripped)
            joined = " ".join(header)
            if joined.endswith(HEADER_SUFFIX):
                match = _HEADER.match(" ".join(joined.split()))
                code = by_alias.get(normalize(match.group(1))) if match else None
                if match is None or code is None:
                    region.errors.append(f"textual-notes header {joined!r} on p{item.page}")
                    block = None
                else:
                    block = (code, int(match.group(2)))
                    region.blocks += 1
                header = []
            k += 1
            continue
        if header:
            region.errors.append(f"unfinished textual-notes header on p{item.page}")
            header = []
        if item.blue and item.bold and item.size == LABEL_SIZE:
            if block is None:
                region.errors.append(f"a note label before any block header on p{item.page}")
                k += 1
                continue
            nxt = items[k + 1] if k + 1 < len(items) else None
            title = nxt is not None and nxt.bold and nxt.stripped == TITLE_WORD
            label = parse_label(item.stripped, *block, title=title)
            if isinstance(label, str):
                region.errors.append(f"{label} on p{item.page}")
                label = Label(item.stripped, LabelKind.VERSE, 0, 0, "", 0)
            own = [item, nxt] if title and nxt is not None else [item]
            region.notes.append(TextualNote(block[0], block[1], label, item.page, own, len(own)))
            k += len(own)
            continue
        if item.stripped and not region.notes:
            region.errors.append(f"text before the first note on p{item.page}")
        elif region.notes:
            region.notes[-1].items.append(item)
        k += 1
    return region


# --- matching ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Pair:
    note: TextualNote
    marker: Marker


@dataclass(slots=True)
class Matching:
    pairs: list[Pair] = field(default_factory=list[Pair])
    markers_without_note: list[Marker] = field(default_factory=list[Marker])
    notes_without_marker: list[TextualNote] = field(default_factory=list[TextualNote])
    letter_errors: list[str] = field(default_factory=list[str])
    next_page: list[str] = field(default_factory=list[str])  # marker links to the next page
    page_errors: list[str] = field(default_factory=list[str])

    @property
    def ok(self) -> bool:
        return not (
            self.markers_without_note
            or self.notes_without_marker
            or self.letter_errors
            or self.page_errors
        )


def _marker_key(marker: Marker) -> float:
    if marker.where is Where.CHAPTER:
        return 0.0
    if marker.where is Where.TITLE:
        return 0.5
    if marker.where is Where.HEADING:
        return marker.verse - 0.5
    return float(marker.verse)


def _note_key(note: TextualNote) -> float:
    if note.label.kind is LabelKind.CHAPTER:
        return 0.0
    if note.label.kind is LabelKind.TITLE:
        return 0.5
    return float(note.label.first)


def accepts(note: TextualNote, marker: Marker, combined: dict[Key, int]) -> bool:
    """Can ``marker`` be the ``*`` behind ``note``?"""
    kind = note.label.kind
    if kind is LabelKind.TITLE:
        return marker.where is Where.TITLE
    if kind is LabelKind.CHAPTER:
        return marker.where is Where.CHAPTER
    if marker.where is Where.HEADING:
        # a heading's * notes the verse the heading stands above, or (as the book labels a
        # speaker heading) the verse before it
        return note.label.first in (marker.verse, marker.verse - 1)
    if marker.where is not Where.VERSE:
        return False
    last = combined.get((marker.book, marker.chapter, marker.verse), marker.verse)
    return marker.verse <= note.label.last and last >= note.label.first


def match(notes: list[TextualNote], markers: list[Marker], combined: dict[Key, int]) -> Matching:
    """Pair notes with markers chapter by chapter, in reading order.

    ``combined``: (book, chapter, stored verse) → the last number a combined entry absorbs.
    """
    result = Matching()
    by_chapter: dict[tuple[str, int], tuple[list[TextualNote], list[Marker]]] = {}
    for note in notes:
        by_chapter.setdefault((note.book, note.chapter), ([], []))[0].append(note)
    for marker in markers:
        by_chapter.setdefault((marker.book, marker.chapter), ([], []))[1].append(marker)
    for chapter_notes, chapter_markers in by_chapter.values():
        ordered = sorted(chapter_markers, key=lambda m: m.ordinal)
        i = j = 0
        while i < len(ordered) and j < len(chapter_notes):
            marker, note = ordered[i], chapter_notes[j]
            if accepts(note, marker, combined):
                result.pairs.append(Pair(note, marker))
                i += 1
                j += 1
            elif _marker_key(marker) < _note_key(note):
                result.markers_without_note.append(marker)
                i += 1
            else:
                result.notes_without_marker.append(note)
                j += 1
        result.markers_without_note += ordered[i:]
        result.notes_without_marker += chapter_notes[j:]
    _check_letters(result)
    for pair in result.pairs:
        note, marker = pair.note, pair.marker
        if marker.target_page == note.page:
            continue
        if marker.target_page == note.page + 1:
            result.next_page.append(note.ref)  # the note starts at the foot of a page
        else:
            result.page_errors.append(f"{note.ref}: * links to p{marker.target_page}")
    return result


def _check_letters(result: Matching) -> None:
    """Each verse's lettered notes ascend, a before b before c, with no letter twice. (A letter
    can also name part of a verse: "2:3b-4" has no "2:3a".)"""
    letters: dict[tuple[str, int, int], list[str]] = {}
    for pair in result.pairs:
        label = pair.note.label
        if label.letter:
            key = (pair.note.book, pair.note.chapter, label.lettered_verse)
            letters.setdefault(key, []).append(label.letter)
    for (book, chapter, verse), seen in letters.items():
        if seen != sorted(set(seen)):
            result.letter_errors.append(f"{book} {chapter}:{verse} letters {''.join(seen)}")


@dataclass(frozen=True, slots=True)
class Anchor:
    verse: int
    char_offset: int
    where: str  # verse · psalm title · chapter header · heading


def anchor(pair: Pair, verse_text: dict[Key, str]) -> Anchor | str:
    """Where a paired note attaches in EMB's verse text, or an error message."""
    marker, label = pair.marker, pair.note.label
    if marker.where is Where.CHAPTER:
        return Anchor(marker.verse, 0, "chapter header")
    if marker.where is Where.TITLE:
        return Anchor(marker.verse, marker.offset, "psalm title")
    if marker.where is Where.HEADING:
        if label.first == marker.verse - 1:
            # the end of the verse before the heading: the spot just above it, and the verse
            # the book's own label names
            text = verse_text.get((marker.book, marker.chapter, marker.verse - 1))
            if text is None:
                return f"{marker.book} {marker.chapter}:{marker.verse - 1} has no text"
            return Anchor(marker.verse - 1, len(text), "heading")
        return Anchor(marker.verse, 0, "heading")
    return Anchor(marker.verse, marker.offset, "verse")
