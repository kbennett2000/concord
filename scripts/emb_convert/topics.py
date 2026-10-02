"""What the Bible Says About: topics of quoted verses (V8-S3b; docs/v8/SPEC.md §4.2).

The feature's section (``articles.sections``: its index's outline entry to the next) opens with
its index — the book's own name for every topic, linking to its page — and then prints the
topics, each a page or more (measured on the PDF):

- a head: the feature's name in bold blue (size 15, linking to the index) over the topic's
  name in bold size 23 (it may wrap to a second line);
- subheads in bold size-9 capitals (one may wrap);
- quotations in size 12: prose at the margin (left 38), poetic lines indented (46; a long one
  wraps back to the margin); a gap of more than a line's pitch opens a new paragraph or
  stanza;
- after each quotation, its reference in size 9, right-aligned in parentheses, linking to the
  verse — one reference, two joined by ";", or one pointing on to another with words between
  (a pointer, linked but not quoted).

Anything else a line can be is an error, so nothing is guessed. The Bible text calls each
topic out with a callout line (``text.FeatureCallout``) naming it as its head prints it and
linking to its page; the topic anchors at the end of the verse the line follows. One the book
never called out would anchor at the start of its first quoted verse. Nothing here holds book
text: it is read from the operator's PDF.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from emb_convert.articles import Section, pick
from emb_convert.layout import Layout, LinkKind
from emb_convert.lines import Line, group_lines
from emb_convert.notetext import NoteText, Piece, emphasis_ok, plain_of, render
from emb_convert.pdfxml import PdfDocument, TextItem
from emb_convert.text import FeatureCallout

OUTLINE = "What the Bible Says About Index"
LABEL = OUTLINE.removesuffix(" Index")
SERIES_SIZE = 15
NAME_SIZE = 23
SUBHEAD_SIZE = 9
REFERENCE_SIZE = 9
TEXT_SIZE = 12
WRAP_RIGHT = 330  # a line reaching this x ran to the right margin
GAP = 20  # more than a line's pitch (14–15 points): a new paragraph or stanza
INDENT = 4  # a line this far right of the part's margin is a poetic line


@dataclass(slots=True)
class Entry:
    name: str  # the index's name for the topic
    page: int  # the page its link targets
    number: int  # its place in the index, from 1


@dataclass(slots=True)
class Quotation:
    lines: list[Line]
    reference: Line


@dataclass(slots=True)
class Part:
    subhead: list[Line]  # empty: quotations before any subhead
    quotations: list[Quotation] = field(default_factory=list[Quotation])


@dataclass(slots=True)
class Topic:
    page: int
    printed: str  # its name as the head prints it
    body: list[Line]
    parts: list[Part]
    entry: Entry | None = None
    callouts: list[FeatureCallout] = field(default_factory=list[FeatureCallout])

    @property
    def title(self) -> str:
        """The index's name for the topic, in normal word order (V8-S5b)."""
        return (
            normal_order(self.entry.name, self.printed) if self.entry is not None else self.printed
        )

    @property
    def number(self) -> int:
        return self.entry.number if self.entry is not None else 0

    @property
    def quotations(self) -> list[Quotation]:
        return [q for part in self.parts for q in part.quotations]


@dataclass(slots=True)
class TopicRegion:
    section: Section | None = None
    entries: list[Entry] = field(default_factory=list[Entry])
    topics: list[Topic] = field(default_factory=list[Topic])
    unindexed: list[Topic] = field(default_factory=list[Topic])
    renamed: list[Topic] = field(default_factory=list[Topic])  # the index words it otherwise
    unmatched_callouts: list[FeatureCallout] = field(default_factory=list[FeatureCallout])
    errors: list[str] = field(default_factory=list[str])


_THE_LAST = re.compile(r"^(.+), (The)$")


def normal_order(name: str, printed: str) -> str:
    """An index sorts a name with "The" last ("Rest, The"); the title turns it back ("The
    Rest") when the topic's own head reads so, the evidence (Kris's call, 2 Oct 2026)."""
    match = _THE_LAST.match(name)
    if match is None:
        return name
    turned = f"{match.group(2)} {match.group(1)}"
    return turned if _key(turned) == _key(printed) else name


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _text(items: Sequence[TextItem]) -> str:
    return " ".join(" ".join(i.text for i in items).split())


def _series(line: Line) -> bool:
    return all(i.size == SERIES_SIZE for i in line.nonblank)


def _name(line: Line) -> bool:
    return any(i.size == NAME_SIZE for i in line.nonblank)


def _head_line(line: Line) -> bool:
    return _series(line) or _name(line)


def _subhead(line: Line) -> bool:
    return all(i.size == SUBHEAD_SIZE and i.bold for i in line.nonblank)


def _quote_line(line: Line) -> bool:
    return all(i.size == TEXT_SIZE and not i.blue and not i.bold for i in line.nonblank)


def find_section(sections: Sequence[Section]) -> Section | None:
    return next((s for s in sections if s.outline == OUTLINE), None)


def parse_topics(doc: PdfDocument, layout: Layout, sections: Sequence[Section]) -> TopicRegion:
    """The index and every topic of the section, each paired with its index entry."""
    region = TopicRegion(section=find_section(sections))
    section = region.section
    if section is None:
        region.errors.append(f"outline lacks the feature index {OUTLINE!r}")
        return region

    def is_reference(line: Line) -> bool:
        return any(
            i.blue
            and i.size == REFERENCE_SIZE
            and i.link_page is not None
            and layout.link_kind(i.link_page) is LinkKind.BIBLE
            for i in line.nonblank
        )

    lines = [
        line
        for line in group_lines([i for i in doc.items if section.holds(i.page)])
        if line.nonblank
    ]
    starts: list[int] = []  # a head: its series line and name lines, in any order
    for n, line in enumerate(lines):
        opens = _head_line(line) and not (n and _head_line(lines[n - 1]))
        if opens and any(_name(lines[k]) for k in range(n, min(n + 3, len(lines)))):
            starts.append(n)
    index = lines[: starts[0]] if starts else lines
    for line in index:
        first = line.nonblank[0]
        target = first.link_page if first.blue else None
        if target is not None and section.holds(target) and target != section.start:
            name = _text([i for i in line.nonblank if i.blue and i.link_page == target])
            region.entries.append(Entry(name, target, len(region.entries) + 1))
    for k, at in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        head_end = at
        while head_end < end and _head_line(lines[head_end]):
            head_end += 1
        head = lines[at:head_end]
        printed = _text([i for line in head for i in line.nonblank if i.size == NAME_SIZE])
        body = lines[head_end:end]
        topic = Topic(head[0].page, printed, body, _parts(body, is_reference, region, printed))
        region.topics.append(topic)
    _index(region)
    return region


def _parts(
    body: list[Line],
    is_reference: Callable[[Line], bool],
    region: TopicRegion,
    printed: str,
) -> list[Part]:
    parts: list[Part] = []
    pending: list[Line] = []
    where = f"WBSA p{body[0].page if body else 0}"
    for n, line in enumerate(body):
        if _subhead(line):
            if pending:
                region.errors.append(f"{where}: a quotation with no reference (p{line.page})")
                pending = []
            if n and _subhead(body[n - 1]):
                parts[-1].subhead.append(line)  # a subhead wrapped onto a second line
            else:
                parts.append(Part([line]))
        elif is_reference(line):
            if not pending:
                region.errors.append(f"{where}: a reference with no quotation (p{line.page})")
                continue
            if not parts:
                parts.append(Part([]))
            parts[-1].quotations.append(Quotation(pending, line))
            pending = []
        elif _quote_line(line):
            pending.append(line)
        else:
            region.errors.append(f"{where}: a line it doesn't print (p{line.page} top {line.top})")
    if pending:
        region.errors.append(f"{where}: its last quotation has no reference")
    for part in parts:
        if not part.quotations:
            region.errors.append(f"{where}: a subhead with no quotation")
    if not parts or not printed:
        region.errors.append(f"{where}: no name or no quotations")
    return parts


def _index(region: TopicRegion) -> None:
    """Pair each topic with its index entry: the entry links to its page (±1) and names it as
    its head prints it, or is the one entry linking to exactly its page (the index can word a
    name otherwise: it puts "The" last for sorting)."""
    free = list(region.entries)
    for topic in region.topics:
        near = [e for e in free if abs(e.page - topic.page) <= 1]
        found = pick(
            [e for e in near if _key(e.name) == _key(topic.printed)],
            [e for e in near if e.page == topic.page],
        )
        if found is None:
            region.unindexed.append(topic)
            continue
        if _key(found.name) != _key(topic.printed):
            region.renamed.append(topic)
        topic.entry = found
        free.remove(found)
    for entry in free:
        region.errors.append(f"WBSA: index entry #{entry.number} (p{entry.page}) names no topic")


def assign_callouts(region: TopicRegion, callouts: Sequence[FeatureCallout]) -> list[int]:
    """Give each callout line into the section to the topic it names: on its target page (±1),
    by the head's or the index's name, or the one starting on exactly that page. Returns the
    callouts' places in ``callouts`` (their reading order), matched or not."""
    section = region.section
    mine: list[int] = []
    for n, callout in enumerate(callouts):
        if section is None or not section.holds(callout.target_page):
            continue
        mine.append(n)
        near = [t for t in region.topics if abs(t.page - callout.target_page) <= 1]
        found = pick(
            [t for t in near if _key(callout.label) in (_key(t.title), _key(t.printed))],
            [t for t in near if t.page == callout.target_page],
        )
        if found is None:
            region.unmatched_callouts.append(callout)
            continue
        found.callouts.append(callout)
    return mine


# --- the text --------------------------------------------------------------------------------


def wrapped(line: Line) -> bool:
    return line.right >= WRAP_RIGHT


def blocks(lines: Sequence[Line]) -> list[list[list[Line]]]:
    """A run of quoted lines → its paragraphs or stanzas (a gap opens one) → their printed
    lines: a poetic line (indented past the run's margin) opens a line of its own, and so does
    a line after one that ended short of the margin; a line after a wrapped one goes on."""
    margin = min((min(i.left for i in line.nonblank) for line in lines), default=0)
    out: list[list[list[Line]]] = []
    previous: Line | None = None
    for line in lines:
        gap = previous is not None and previous.page == line.page and line.top - previous.top > GAP
        poetic = min(i.left for i in line.nonblank) > margin + INDENT
        if not out or gap:
            out.append([[line]])
        elif poetic or previous is None or not wrapped(previous):
            out[-1].append([line])
        else:
            out[-1][-1].append(line)
        previous = line
    return out


Inline = Callable[[Sequence[Line]], list[Piece]]
Relink = Callable[[list[Piece]], tuple[list[Piece], list[str]]]


@dataclass(slots=True)
class Written:
    markdown: str
    plain: str  # blocks apart by blank lines (hygiene runs on it)
    printed: str  # every character the body prints, spaces aside (the consistency check)
    problems: list[str] = field(default_factory=list[str])
    counts: Counter[str] = field(default_factory=Counter[str])


class Writer:
    """Markdown from lines, unit by unit, each unit checked (flanking, round trip)."""

    def __init__(self, inline: Inline, relink: Relink) -> None:
        self.inline = inline
        self.relink = relink
        self.printed: list[str] = []
        self.problems: list[str] = []

    def unit(self, lines: Sequence[Line], *, heading: bool = False) -> NoteText:
        pieces = self.inline(lines)
        self.printed.append(" ".join(p.text for p in pieces))
        if heading:  # a heading is bold already; its weight stays out of the Markdown
            pieces = [Piece(p.text, False, p.run, False) for p in pieces]
        pieces, targets = self.relink(pieces)
        rendered = render(pieces, targets, always=True)
        assert rendered.markdown is not None
        if not emphasis_ok(rendered.markdown):
            self.problems.append("emphasis-flanking")
        if plain_of(rendered.markdown) != rendered.plain:
            self.problems.append("markdown-round-trip")
        return rendered

    def quoted(self, lines: Sequence[Line], counts: Counter[str]) -> tuple[list[str], list[str]]:
        """Quoted lines → (Markdown, plain) paragraphs; a paragraph's printed lines are apart by
        hard breaks."""
        markdown: list[str] = []
        plain: list[str] = []
        for block in blocks(lines):
            counts["paragraphs or stanzas"] += 1
            if len(block) > 1:
                counts["printed lines (hard breaks)"] += len(block)
            texts = [self.unit(group) for group in block]
            markdown.append("\\\n".join(_md(t) for t in texts))
            plain.append("\n".join(t.plain for t in texts))
        return markdown, plain

    def done(self, markdown: list[str], plain: list[str]) -> Written:
        return Written(
            "\n\n".join(markdown),
            "\n\n".join(plain),
            re.sub(r"\s+", "", " ".join(self.printed)),
            self.problems,
        )


def _md(text: NoteText) -> str:
    assert text.markdown is not None
    return text.markdown


def write(topic: Topic, inline: Inline, relink: Relink) -> Written:
    """The topic as Markdown: each subhead a ``###`` heading, each quotation its paragraphs
    with its reference on a hard-break line under the last."""
    writer = Writer(inline, relink)
    markdown: list[str] = []
    plain: list[str] = []
    counts: Counter[str] = Counter()
    for part in topic.parts:
        if part.subhead:
            head = writer.unit(part.subhead, heading=True)
            markdown.append(f"### {_md(head)}")
            plain.append(head.plain)
            counts["subheads"] += 1
        for quotation in part.quotations:
            counts["quotations"] += 1
            md, pl = writer.quoted(quotation.lines, counts)
            reference = writer.unit([quotation.reference])
            md[-1] += f"\\\n{_md(reference)}"
            pl[-1] += f"\n{reference.plain}"
            markdown += md
            plain += pl
    written = writer.done(markdown, plain)
    written.counts = counts
    return written
