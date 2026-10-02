"""The Perspectives boxes (V8-S3b; docs/v8/SPEC.md §4.2).

A box stands inside the Bible text and is never part of a verse (``text.PerspectivesBox``
records its lines and where it stands). It prints, measured on the PDF:

- its label (size 9, blue, linking to the Perspectives Index);
- the passage it quotes (size 12);
- the passage's reference in small capitals (size 7, blue, linking to the verse);
- a person's words (size 12);
- the attribution in small capitals (size 7; it may wrap, and a title in it is italic).

The index names each box by its author and passage, the name linking to the box's page (±1:
a box can open at the top of the next page). A box anchors where it stands — S3a's rule: at
the end of the verse it follows when that is its passage's first verse or later, else at the
start of the verse it precedes. Nothing here holds book text: it is read from the
operator's PDF.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from emb_convert.articles import Section, parse_reference, pick
from emb_convert.clean import collapse
from emb_convert.layout import Layout, LinkKind
from emb_convert.lines import Line, group_lines
from emb_convert.pdfxml import PdfDocument
from emb_convert.study import Part
from emb_convert.text import PerspectivesBox
from emb_convert.topics import Inline, Relink, Writer, Written

OUTLINE = "Perspectives Index"
LABEL = OUTLINE.removesuffix(" Index")
REFERENCE_SIZE = 7
INDEX_SIZE = 12


@dataclass(slots=True)
class Entry:
    name: str  # the index's name for the box: its author
    page: int  # the page the name links to
    reference: str  # the passage as the index prints it


@dataclass(slots=True)
class Box:
    record: PerspectivesBox
    reference: str  # the passage as the box prints it
    parts: list[tuple[str, Part]]
    quote: list[Line]  # the passage it quotes
    reference_line: Line
    words: list[Line]  # the person's words
    attribution: list[Line]
    entry: Entry | None = None

    @property
    def book(self) -> str:
        return self.record.book

    @property
    def page(self) -> int:
        return self.record.page

    @property
    def name(self) -> str:
        """The box in findings and cross-check keys: the feature and its printed passage."""
        return f"PERSP {title_case(self.reference)}"

    @property
    def body(self) -> list[Line]:
        return [*self.quote, self.reference_line, *self.words, *self.attribution]


@dataclass(slots=True)
class BoxRegion:
    section: Section | None = None
    entries: list[Entry] = field(default_factory=list[Entry])
    boxes: list[Box] = field(default_factory=list[Box])
    unindexed: list[Box] = field(default_factory=list[Box])
    index_differs: list[Box] = field(default_factory=list[Box])  # the index prints another passage
    errors: list[str] = field(default_factory=list[str])


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def title_case(text: str) -> str:
    """ "1 KINGS 19:3-4" → "1 Kings 19:3-4" (same length, so a link's slices still fit)."""
    return re.sub(
        r"[A-Za-z]+",
        lambda m: "of" if m.group(0).lower() == "of" else m.group(0).capitalize(),
        text,
    )


def parse_boxes(
    records: Sequence[PerspectivesBox],
    doc: PdfDocument,
    layout: Layout,
    sections: Sequence[Section],
    by_alias: dict[str, str],
    last_verse: dict[tuple[str, int], int],
) -> BoxRegion:
    """Every box the text pass set aside, split into its parts and paired with its index
    entry."""
    region = BoxRegion(section=next((s for s in sections if s.outline == OUTLINE), None))
    section = region.section
    if section is None:
        region.errors.append(f"outline lacks the feature index {OUTLINE!r}")
        return region
    for line in group_lines([i for i in doc.items if section.holds(i.page)]):
        content = line.nonblank
        if not content or not (content[0].blue and content[0].size == INDEX_SIZE):
            continue
        cut = next((n for n, i in enumerate(content) if not i.blue), len(content))
        name = collapse("".join(i.text for i in content[:cut])).strip()
        reference = collapse("".join(i.text for i in content[cut:] if i.blue)).strip()
        region.entries.append(Entry(name, content[0].link_page or 0, reference))

    def is_reference(line: Line) -> bool:
        return any(
            i.size == REFERENCE_SIZE
            and i.blue
            and i.link_page is not None
            and layout.link_kind(i.link_page) is LinkKind.BIBLE
            for i in line.nonblank
        )

    for record in records:
        where = f"Perspectives box {record.book} p{record.page}"
        lines = record.lines[1:]  # its label first
        at = next((n for n, line in enumerate(lines) if is_reference(line)), None)
        if at is None:
            region.errors.append(f"{where}: no reference")
            continue
        end = len(lines)
        while end > at + 1 and all(
            i.size == REFERENCE_SIZE and not i.blue for i in lines[end - 1].nonblank
        ):
            end -= 1
        quote, words, attribution = lines[:at], lines[at + 1 : end], lines[end:]
        if not quote or not words or not attribution:
            region.errors.append(f"{where}: no quotation, words or attribution")
            continue
        printed = collapse(lines[at].text).strip()
        parts = parse_reference(title_case(printed), by_alias, last_verse)
        if isinstance(parts, str):
            region.errors.append(f"{where}: reference {parts}")
            continue
        if any(book != record.book for book, _ in parts):
            region.errors.append(f"{where}: its passage names another book")
            continue
        region.boxes.append(Box(record, printed, parts, quote, lines[at], words, attribution))
    _index(region)
    return region


def _index(region: BoxRegion) -> None:
    """Pair each box with its index entry: the entry's name links to its page (±1) and the
    entry prints its passage, or it is the one entry linking to exactly its page."""
    free = list(region.entries)
    for box in region.boxes:
        near = [e for e in free if abs(e.page - box.page) <= 1]
        found = pick(
            [e for e in near if _key(e.reference) == _key(box.reference)],
            [e for e in near if e.page == box.page],
        )
        if found is None:
            region.unindexed.append(box)
            continue
        if _key(found.reference) != _key(box.reference):
            region.index_differs.append(box)
        box.entry = found
        free.remove(found)
    for entry in free:
        region.errors.append(f"Perspectives: index entry on p{entry.page} names no box")


@dataclass(frozen=True, slots=True)
class Anchor:
    book: str
    chapter: int
    verse: int  # a number the verse text is stored under
    at_end: bool  # at the end of the verse (char_offset = its length), else at its start
    outside: bool  # the anchor verse lies outside the box's passage


def anchor(box: Box, stored: dict[tuple[str, int, int], int]) -> Anchor | str:
    """Where the box's note goes: where the box stands (S3a's rule)."""
    record = box.record
    parts = [part for _, part in box.parts]
    first = min((p.start_chapter, p.start_verse) for p in parts)
    if record.after is not None and record.after >= first:
        (chapter, verse), at_end = record.after, True
    elif record.before is not None and record.before[0] == record.book:
        _, chapter, verse = record.before
        at_end = False
    else:
        return "no verse to stand by in its book"
    covered = any(
        (p.start_chapter, p.start_verse) <= (chapter, verse) <= (p.end_chapter, p.end_verse)
        for p in parts
    )
    stored_verse = stored.get((record.book, chapter, verse), verse)
    return Anchor(record.book, chapter, stored_verse, at_end, not covered)


def shape(box: Box, last_verse: dict[tuple[str, int], int]) -> str:
    """multi-part · whole chapter · verse · range (as the spec counts them)."""
    if len(box.parts) > 1:
        return "multi-part"
    book, part = box.parts[0]
    if part.start_chapter != part.end_chapter:
        return "cross-chapter"
    if part.start_verse == part.end_verse:
        return "verse"
    if part.start_verse == 1 and part.end_verse == last_verse.get((book, part.end_chapter)):
        return "whole chapter"
    return "range"


def write(box: Box, inline: Inline, relink: Relink) -> Written:
    """The box as Markdown: its quotation of the passage, the reference on a hard-break line
    under it, the person's words, the attribution."""
    writer = Writer(inline, relink)
    counts: Counter[str] = Counter()
    markdown, plain = writer.quoted(box.quote, counts)
    reference = writer.unit([box.reference_line])
    assert reference.markdown is not None
    markdown[-1] += f"\\\n{reference.markdown}"
    plain[-1] += f"\n{reference.plain}"
    md, pl = writer.quoted(box.words, counts)
    attribution = writer.unit(box.attribution)
    assert attribution.markdown is not None
    written = writer.done([*markdown, *md, attribution.markdown], [*plain, *pl, attribution.plain])
    written.counts = counts
    return written
