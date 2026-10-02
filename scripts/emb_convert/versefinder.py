"""EMB's Tyndale Verse Finder (V8-S6b; docs/v8/SPEC.md §4.5, ADR-0013).

The Verse Finder is the front section where most lines carry a link (``documents.find_front``'s
reference section). Read by print style, never by words:

- its **title**: the title-size line, checked against the outline name;
- its **index**: one link per topic, each to the topic's page — navigation, paired with the
  topics and not copied;
- a **topic**: a bold line at the margin, its name; a bold-italic run on that line is its
  pointer, whose links name other topics by their pages. A pointer on a topic with no entries is
  a "see" redirect; on a topic with entries, a "see also";
- an **entry**: an indented line, with the margin lines that carry it on: a statement and one
  reference in parentheses, the reference a link to its passage's page.

Two outputs:

- **The topics** (``topics/EMB.json``, the topics contract): every topic, its id ``vf-<n>`` (its
  place in the book), its name, its section (the name's first letter), its verses (every
  reference expanded verse by verse — a range, a whole chapter, a list — less any verse the NLT
  omits) and, for a redirect, its first target as ``see_also``. The contract can't hold the
  statements or a "see also" between topics with verses (``see_also`` is a redirect), so:
- **The document** (``front-matter-6``): the Verse Finder as printed — each topic ``## <name>``,
  its pointer an italic paragraph, its entries a ``- `` list, each reference a ``ref:`` link.

A reference is read with ``study.resolve_run``; the book's own link page is evidence, as for the
reading plan. Nothing here holds book text: it is read from the operator's PDF at run time.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from emb_convert.clean import Fixes
from emb_convert.documents import (
    MARGIN,
    Blocks,
    Section,
    Witnessed,
    hygiene,
    is_link_line,
    left,
    letters,
    md,
    title_agrees,
    title_lines,
)
from emb_convert.lines import Line
from emb_convert.notes import Context
from emb_convert.notetext import Piece, assemble, plain_text, relink, run_texts
from emb_convert.readingplan import link_evidence
from emb_convert.study import exists, link_runs, resolve_run, target_verses

SOURCE = "Tyndale Verse Finder"
PREFIX = "vf-"
KIND = "front-matter"
SLUG = "front-matter-6"
ORDINAL = 6  # after the five front-matter pieces (V8-S5c), in print order

Key = tuple[str, int, int]
Verse = tuple[str, int, int]

_ID = re.compile(rf"{PREFIX}[1-9][0-9]*")


def key(topic: int) -> Key:
    return (f"VF topic {topic}", 0, 1)


def topic_id(number: int) -> str:
    return f"{PREFIX}{number}"


@dataclass(slots=True)
class Entry:
    lines: list[Line]
    targets: list[str] = field(default_factory=list[str])  # one per reference part
    evidence: str = "unexplained"  # the book's link page: agrees · a page off · unexplained


@dataclass(slots=True)
class Topic:
    number: int
    head: Line
    entries: list[Entry] = field(default_factory=list[Entry])
    pointer: list[tuple[str, int | None]] = field(default_factory=list[tuple[str, int | None]])
    targets: list[int] = field(default_factory=list[int])  # the pointer's topics, by number
    name: str = ""

    @property
    def page(self) -> int:
        return self.head.page

    @property
    def lines(self) -> list[Line]:
        return [self.head, *(line for entry in self.entries for line in entry.lines)]


@dataclass(slots=True)
class FinderFindings:
    """The Verse Finder (V8-S6b): found, written and checked."""

    payload: dict[str, object] | None = None
    document: dict[str, object] | None = None
    pages: int = 0
    index: list[int | None] = field(default_factory=list[int | None])  # each entry's link page
    topics: list[Topic] = field(default_factory=list[Topic])
    other_lines: int = 0  # lines of no form the Verse Finder prints (sub-entries, …): target 0
    shapes: Counter[str] = field(default_factory=Counter[str])
    lists: int = 0  # references printing more than one part ("C:V, V")
    evidence: Counter[str] = field(default_factory=Counter[str])
    omitted: list[str] = field(default_factory=list[str])  # a verse the NLT omits, skipped
    repeats: int = 0  # a verse cited twice under one topic, kept once
    links: int = 0  # topic–verse links written
    words: int = 0
    size: int = 0  # the document's Markdown bytes
    fixes: Counter[str] = field(default_factory=Counter[str])
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])
    witnessed: Witnessed = field(default_factory=Witnessed)

    @property
    def entries(self) -> int:
        return sum(len(t.entries) for t in self.topics)

    @property
    def references(self) -> int:
        return sum(1 for t in self.topics for e in t.entries if e.targets)

    @property
    def redirects(self) -> list[Topic]:
        return [t for t in self.topics if t.pointer and not t.entries]

    @property
    def see_also(self) -> list[Topic]:
        return [t for t in self.topics if t.pointer and t.entries]

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and self.payload is not None
            and self.document is not None
            and not self.other_lines
            and not any(self.hygiene.values())
            and not self.evidence["unexplained"]
        )


def _is_head(line: Line) -> bool:
    content = line.nonblank
    return left(line) <= MARGIN and content[0].bold and not content[0].italic


def _read(found: FinderFindings, body: list[Line]) -> None:
    """The index (before the first topic), then each topic's head and entries."""
    for line in body:
        if _is_head(line):
            found.topics.append(Topic(len(found.topics) + 1, line))
        elif not found.topics and is_link_line(line):
            found.index.append(next((i.link_page for i in line.nonblank if i.link_page), None))
        elif found.topics and left(line) > MARGIN:
            found.topics[-1].entries.append(Entry([line]))
        elif found.topics and found.topics[-1].entries and not line.nonblank[0].bold:
            found.topics[-1].entries[-1].lines.append(line)
        else:
            found.other_lines += 1
            found.errors.append(
                f"VF p{line.page} top {line.top}: a line the finder doesn't explain"
            )


def _pair(found: FinderFindings) -> None:
    """Each index entry links to its topic's page, in order; each pointer names topics by their
    pages, and its words are the named topic's (letters only: one prints a space as a hyphen)."""
    pages = [t.page for t in found.topics]
    if found.index != pages:
        found.errors.append(
            f"VF: the index ({len(found.index)} links) doesn't pair with the topics "
            f"({len(found.topics)}) page by page"
        )
    by_page = {t.page: t for t in found.topics}
    for topic in found.topics:
        for words, page in topic.pointer:
            target = by_page.get(page) if page is not None else None
            if target is None or target is topic:
                found.errors.append(f"VF topic {topic.number}: a pointer to no topic (p{page})")
                continue
            if letters(words) != letters(target.name):
                found.errors.append(
                    f"VF topic {topic.number}: a pointer's words aren't topic {target.number}'s"
                )
            topic.targets.append(target.number)


def _pointer(head: Line) -> list[tuple[str, int | None]]:
    """The pointer's links: consecutive blue italic items to one page are one target."""
    out: list[tuple[str, int | None]] = []
    previous = False
    for item in head.items:
        linked = item.blue and item.italic
        if linked and previous and out and item.link_page in (None, out[-1][1]):
            out[-1] = (out[-1][0] + item.text, out[-1][1])
        elif linked:
            out.append((item.text, item.link_page))
        if item.stripped:
            previous = linked
    return [(" ".join(words.split()), page) for words, page in out]


def _shape(target: str) -> str:
    (_, c1, v1), (_, c2, v2) = target_verses(target)
    if "." not in target.split(".", 1)[1]:
        return "a whole chapter"
    if (c1, v1) == (c2, v2):
        return "a verse"
    return "verses in one chapter" if c1 == c2 else "across chapters"


def _verses(target: str, ctx: Context, found: FinderFindings, where: str) -> list[Verse]:
    """Every verse a target names, in order: a whole chapter to its end, a range across chapters
    through each chapter's end. A verse EMB holds (or absorbs into a combined entry) is kept by
    its canonical number; one the NLT omits is skipped and listed."""
    (book, c1, v1), (_, c2, v2) = target_verses(target)
    whole = "." not in target.split(".", 1)[1]
    out: list[Verse] = []
    for chapter in range(c1, c2 + 1):
        end = max(ctx.skeleton.get((book, chapter), 0), ctx.last_verse.get((book, chapter), 0))
        first = v1 if chapter == c1 and not whole else 1
        last = v2 if chapter == c2 and not whole else end
        for verse in range(first, last + 1):
            if (book, chapter, verse) in ctx.stored:
                out.append((book, chapter, verse))
            elif exists(ctx.skeleton, book, chapter, verse):
                found.omitted.append(f"{where} → {target} ({book} {chapter}:{verse})")
            else:
                found.errors.append(f"{where}: {target} names no verse {book} {chapter}:{verse}")
    return out


def build_finder(sections: Sequence[Section], ctx: Context) -> FinderFindings:
    """The Verse Finder's section → its topics, its document, their checks and its witness."""
    found = FinderFindings()
    if len(sections) != 1:
        found.errors.append(f"VF: {len(sections)} reference sections in the front, not one")
        return found
    section = sections[0]
    found.pages = section.end - section.start
    taken, subtitle = title_lines(section)
    if not title_agrees(section, taken) or subtitle:
        found.errors.append(f"VF p{section.start}: its printed title isn't its outline name")
    _read(found, section.body)
    scratch: Counter[str] = Counter()

    def pieces(
        lines: Sequence[Line],
        counts: Counter[str],
        *,
        skip: frozenset[int] = frozenset(),
        run_of: dict[int, int] | None = None,
    ) -> list[Piece]:
        return assemble(
            lines, ctx.vocabulary, Fixes(), counts, repair=ctx.repair, skip=skip, run_of=run_of
        )

    for topic in found.topics:
        topic.pointer = _pointer(topic.head)
        italic = frozenset(id(i) for i in topic.head.items if i.italic)
        topic.name = plain_text(pieces([topic.head], scratch, skip=italic))
    _pair(found)
    blocks = Blocks(lambda lines: pieces(lines, found.fixes))
    payload = [_write(found, blocks, topic, ctx, pieces) for topic in found.topics]
    lines = [line for topic in found.topics for line in topic.lines]
    if not blocks.holds(pieces(lines, scratch)):
        found.errors.append("VF: its blocks don't hold exactly the text it prints")
    hygiene(found.hygiene, "VF", blocks.text_plain, lines, ctx, blocks.problems)
    ids = [str(t["id"]) for t in payload]
    if not all(_ID.fullmatch(i) for i in ids) or len(set(ids)) != len(ids):
        found.errors.append("VF: a topic id isn't vf-<n>, or repeats")
    found.payload = {"source": SOURCE, "topics": payload}
    found.words = len(blocks.text_plain.split())
    text = blocks.document
    found.size = len(text.encode("utf-8"))
    found.document = {
        "slug": SLUG,
        "kind": KIND,
        "title": section.title,
        "ordinal": ORDINAL,
        "text": text,
    }
    return found


class Pieces(Protocol):
    def __call__(
        self,
        lines: Sequence[Line],
        counts: Counter[str],
        *,
        skip: frozenset[int] = ...,
        run_of: dict[int, int] | None = ...,
    ) -> list[Piece]: ...


def _write(
    found: FinderFindings, blocks: Blocks, topic: Topic, ctx: Context, pieces: Pieces
) -> dict[str, object]:
    """One topic: its head, its pointer and its entries as blocks; its verses; its payload."""
    where = f"VF topic {topic.number}"
    italic = frozenset(id(i) for i in topic.head.items if i.italic)
    roman = frozenset(id(i) for i in topic.head.items if not i.italic)
    head = blocks.text(pieces=pieces([topic.head], found.fixes, skip=italic), plain_style=True)
    blocks.add(f"## {md(head)}", head.plain)
    if topic.pointer:
        words = blocks.text(pieces=pieces([topic.head], found.fixes, skip=roman))
        blocks.add(md(words), words.plain)
    verses: dict[Verse, None] = {}
    cited = 0
    items: list[str] = []
    plains: list[str] = []
    for entry in topic.entries:
        run_of, runs = link_runs(entry.lines)
        flat = pieces(entry.lines, found.fixes, run_of=run_of)
        texts = run_texts(flat)
        if len(texts) != 1:
            found.errors.append(f"{where}: an entry with {len(texts)} references, not one")
            continue
        ((run, text),) = texts.items()
        refs = resolve_run(
            text,
            note_book="",
            continues=None,
            page_book=ctx.page_book(runs[run].page),
            by_alias=ctx.by_alias,
            names=ctx.names,
        )
        if isinstance(refs, str) or not refs.named:
            found.errors.append(f"{where}: {refs if isinstance(refs, str) else 'no book named'}")
            continue
        entry.targets = [p.target for p in refs.parts]
        if len(refs.parts) > 1:
            found.lists += 1
        for target in entry.targets:
            found.shapes[_shape(target)] += 1
            for verse in _verses(target, ctx, found, where):
                cited += 1
                verses[verse] = None
        entry.evidence = link_evidence(entry.targets[0], runs[run].page, ctx)
        found.evidence[entry.evidence] += 1
        linked, targets = relink(flat, {run: [(p.start, p.end, p.target) for p in refs.parts]})
        written = blocks.text(pieces=linked, targets=targets)
        items.append(f"- {md(written)}")
        plains.append(written.plain)
    if items:
        blocks.add("\n".join(items), "\n".join(plains))
    found.repeats += cited - len(verses)
    found.links += len(verses)
    redirect = topic.targets[0] if topic.targets and not topic.entries else None
    _witness(found, topic, ctx)
    return {
        "id": topic_id(topic.number),
        "name": topic.name,
        "section": topic.name[:1].upper(),
        "see_also": topic_id(redirect) if redirect is not None else None,
        "verses": [{"book": b, "chapter": c, "verse": v} for b, c, v in verses],
    }


def _witness(found: FinderFindings, topic: Topic, ctx: Context) -> None:
    lines = topic.lines
    scratch: Counter[str] = Counter()

    def plain(fixes: Fixes) -> str:
        return plain_text(assemble(lines, ctx.vocabulary, fixes, scratch, repair=ctx.repair))

    found.witnessed.add(key(topic.number), lines, plain)
