"""EMB's One Year Reading Plan as a document (V8-S5c; docs/v8/SPEC.md §4.3, ADR-0012).

The plan is the front section whose every line but its title is a link
(``documents.find_front``). Read by print style:

- its **title**: the title-size line, checked against the outline name;
- the **month list**: links at the margin before the first day, each to a month's first page —
  navigation, set aside and counted;
- a **day**: a bold link line (the date; its link back to the plan's top is dropped) over its
  **readings**: indented links, one per line, each to its passage's page.

A day is ``## <date as printed>`` over a ``- `` list of its readings, each a ``ref:`` link.
A reading is read with ``study.resolve_run``. One that runs on into the next book (an em dash
between two references) becomes two links, the text unchanged: the rest of the first book, then
the second book from its start. A part-verse letter (":73a") stays in the link's text while the
target takes the whole verse (ADR-0011's grammar has no part-verse). Every target's first and
last verse must exist (the skeleton, as for the notes' links); a target ending on a verse the
NLT omits is listed. The book's own link page is evidence: it stands on the reading's first
verse's page, or one page off.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from emb_convert.clean import Fixes
from emb_convert.documents import (
    MARGIN,
    Blocks,
    Section,
    Witnessed,
    hygiene,
    left,
    md,
    title_agrees,
    title_lines,
)
from emb_convert.lines import Line
from emb_convert.notes import Context
from emb_convert.notetext import Piece, assemble, plain_text
from emb_convert.study import RefPart, exists, resolve_run, target_verses

KIND = "reading-plan"
SLUG = "reading-plan-1"
EM_DASH = "—"
SINGLE_CHAPTER = frozenset({"OBA", "PHM", "2JN", "3JN", "JUD"})

Key = tuple[str, int, int]

# a part-verse letter after a verse number, before a range's dash or the reading's end
_PART_VERSE = re.compile(r"(?<=\d)[ab](?=[-–]|$)")


def key(day: int) -> Key:
    return (f"PLAN day {day}", 0, 1)


@dataclass(slots=True)
class Reading:
    line: Line
    text: str  # as printed
    links: list[tuple[str, str]]  # (its text, target), one per reference
    shape: str
    evidence: str  # agrees · a page off · unexplained


@dataclass(slots=True)
class Day:
    line: Line
    readings: list[Reading] = field(default_factory=list[Reading])


@dataclass(slots=True)
class PlanFindings:
    """EMB's One Year Reading Plan (V8-S5c): found, written and checked."""

    document: dict[str, object] | None = None
    days: list[Day] = field(default_factory=list[Day])
    months: int = 0  # the month list's links, set aside
    capitals: int = 0  # dates printed in capitals (a month's first day)
    shapes: Counter[str] = field(default_factory=Counter[str])
    evidence: Counter[str] = field(default_factory=Counter[str])
    cross_book: list[str] = field(default_factory=list[str])
    part_verse: list[str] = field(default_factory=list[str])
    omitted: list[str] = field(default_factory=list[str])  # a target ending on a verse EMB lacks
    links: int = 0
    words: int = 0
    size: int = 0  # the Markdown's bytes
    fixes: Counter[str] = field(default_factory=Counter[str])
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])
    witnessed: Witnessed = field(default_factory=Witnessed)

    @property
    def readings(self) -> int:
        return sum(len(d.readings) for d in self.days)

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and self.document is not None
            and not any(self.hygiene.values())
            and not self.evidence["unexplained"]
        )


def _ref(book: str, c1: int, v1: int, c2: int, v2: int) -> str:
    if (c1, v1) == (c2, v2):
        return f"{book}.{c1}.{v1}"
    if c1 == c2:
        return f"{book}.{c1}.{v1}-{v2}"
    return f"{book}.{c1}.{v1}-{c2}.{v2}"


def _shape(part: RefPart) -> str:
    if part.book in SINGLE_CHAPTER:
        return "a one-chapter book's verses"
    (_, c1, v1), (_, c2, v2) = target_verses(part.target)
    if "." not in part.target.split(".", 1)[1]:
        return "whole chapters"
    if (c1, v1) == (c2, v2):
        return "a verse"
    return "verses in one chapter" if c1 == c2 else "across chapters"


def resolve(text: str, ctx: Context) -> tuple[list[tuple[str, str]], str, list[str]] | str:
    """A reading as printed → its links (text, target), its shape and the part-verse letters it
    prints; or an error message."""
    halves = text.split(EM_DASH)
    if len(halves) > 2:
        return f"reading {text!r}: more than one book change"
    parts: list[RefPart] = []
    letters: list[str] = []
    for half in halves:
        clean, n = _PART_VERSE.subn("", half)
        if n:
            letters.append(half)
        refs = resolve_run(
            clean,
            note_book="",
            continues=None,
            page_book=None,
            by_alias=ctx.by_alias,
            names=ctx.names,
        )
        if isinstance(refs, str):
            return refs
        if len(refs.parts) != 1 or not refs.named:
            return f"reading {text!r}: not one named reference"
        parts.append(refs.parts[0])
    if len(parts) == 1:
        return [(text, parts[0].target)], _shape(parts[0]), letters
    first, second = parts
    order = [b.code for b in ctx.layout.books]
    if order.index(second.book) != order.index(first.book) + 1:
        return f"reading {text!r}: its second book doesn't follow its first"
    last_chapter = max(c for b, c in ctx.last_verse if b == first.book)
    rest = _ref(
        first.book,
        first.chapter,
        first.verse,
        last_chapter,
        ctx.last_verse[(first.book, last_chapter)],
    )
    _, (_, c2, v2) = target_verses(second.target)
    opening = _ref(second.book, 1, 1, c2, v2)
    return [(halves[0], rest), (halves[1], opening)], "into the next book", letters


def link_evidence(target: str, page: int | None, ctx: Context) -> str:
    """Where the book's own link page stands against a target's first verse (also the Verse
    Finder's, V8-S6b): on its page, one page off, or unexplained."""
    book, chapter, verse = target_verses(target)[0]
    stored = ctx.stored.get((book, chapter, verse))
    span = ctx.verse_pages.get((book, chapter, stored)) if stored is not None else None
    if page is None or span is None or ctx.page_book(page) != book:
        return "unexplained"
    if span[0] <= page <= span[1]:
        return "agrees"
    return "a page off" if span[0] - 1 <= page <= span[1] + 1 else "unexplained"


def _read(found: PlanFindings, body: list[Line]) -> None:
    for line in body:
        content = line.nonblank
        if all(i.bold for i in content):
            found.days.append(Day(line))
        elif found.days and left(line) > MARGIN:
            found.days[-1].readings.append(
                Reading(line, " ".join(line.text.split()), [], "", "unexplained")
            )
        elif not found.days and left(line) <= MARGIN:
            found.months += 1
        else:
            found.errors.append(
                f"PLAN p{line.page} top {line.top}: a line the plan doesn't explain"
            )


def build_plan(section: Section, ctx: Context) -> PlanFindings:
    """The plan section → its document, its readings' links and their checks."""
    found = PlanFindings()
    taken, subtitle = title_lines(section)
    if not title_agrees(section, taken) or subtitle:
        found.errors.append(f"PLAN p{section.start}: its printed title isn't its outline name")
    _read(found, section.body)

    def inline(lines: Sequence[Line]) -> list[Piece]:
        return assemble(lines, ctx.vocabulary, Fixes(), found.fixes, repair=ctx.repair, bold=True)

    blocks = Blocks(inline)
    lines: list[Line] = []
    for number, day in enumerate(found.days, 1):
        lines += [day.line, *(r.line for r in day.readings)]
        found.capitals += 1 if day.line.text.upper() == day.line.text else 0
        date = blocks.text([day.line], plain_style=True)
        blocks.add(f"## {md(date)}", date.plain)
        items: list[str] = []
        plains: list[str] = []
        for reading in day.readings:
            reading.text = plain_text(inline([reading.line]))
            resolved = resolve(reading.text, ctx)
            if isinstance(resolved, str):
                found.errors.append(f"{date.plain}: {resolved}")
                continue
            reading.links, reading.shape, letters = resolved
            found.shapes[reading.shape] += 1
            if reading.shape == "into the next book":
                found.cross_book.append(reading.text)
            found.part_verse += letters
            pieces = [Piece(reading.links[0][0], run=0)]
            if len(reading.links) > 1:
                pieces += [Piece(EM_DASH), Piece(reading.links[1][0], run=1)]
            targets = [target for _, target in reading.links]
            for target in targets:
                for b, c, v in target_verses(target):
                    if not exists(ctx.skeleton, b, c, v):
                        found.errors.append(f"{date.plain}: {reading.text} → {target}: no verse")
                    elif (b, c, v) not in ctx.stored:
                        found.omitted.append(f"{reading.text} ({b} {c}:{v})")
            first = next((i.link_page for i in reading.line.nonblank if i.link_page), None)
            reading.evidence = link_evidence(targets[0], first, ctx)
            found.evidence[reading.evidence] += 1
            found.links += len(targets)
            text = blocks.text(pieces=pieces, targets=targets)
            items.append(f"- {md(text)}")
            plains.append(text.plain)
        blocks.add("\n".join(items), "\n".join(plains))
        _witness(found, number, day, date.plain, ctx)
    if not blocks.holds(inline(lines)):
        found.errors.append("PLAN: its blocks don't hold exactly the text it prints")
    hygiene(found.hygiene, "PLAN", blocks.text_plain, lines, ctx, blocks.problems)
    found.words = len(blocks.text_plain.split())
    text = blocks.document
    found.size = len(text.encode("utf-8"))
    found.document = {
        "slug": SLUG,
        "kind": KIND,
        "title": section.title,
        "ordinal": 1,
        "text": text,
    }
    return found


def _witness(found: PlanFindings, number: int, day: Day, date: str, ctx: Context) -> None:
    lines = [day.line, *(r.line for r in day.readings)]
    scratch: Counter[str] = Counter()

    def plain(fixes: Fixes) -> str:
        pieces = assemble(lines, ctx.vocabulary, fixes, scratch, repair=ctx.repair, bold=True)
        return plain_text(pieces)

    found.witnessed.add(key(number), lines, plain, opening=date)
