"""EMB's front matter as documents (V8-S5c; docs/v8/SPEC.md §4.3, ADR-0012).

Five pieces in print order (``documents.find_front``): the copyright page, then each front
section that is neither the reading plan nor a reference section. Each is read by print style
only, with the reader its layout calls for:

- **the copyright page** (small type; the book prints no title for it): paragraphs split by a
  gap, or by a page turn after a short line; a paragraph's lines join while each runs to the
  right margin; a paragraph of two or more units (a line and the lines its wrap carries) is a
  ``- `` list, as S5b's margin text;
- **prose** (any other layout): a bold line at the margin is a head
  (``##``); a paragraph runs while its lines wrap, opening at the paragraph indent, after a
  head or a gap, or at a page's top; a line opening with a bullet starts a list item, its wrap
  set at the hanging indent, and an item's own further paragraph opens deeper still (an
  indented paragraph inside the item); a right-set italic line is the signature (a paragraph);
- **roles** (every line centred): an italic role (a wrapped role runs on to the next italic
  line) over its names, one per line — a paragraph, the role in italics, each name on a line
  of its own (hard breaks);
- **people** (a group label at the margin): a bold line is a division head (``##``); an italic
  line in capitals a group label (an italic paragraph) over its people, one per line (a ``- ``
  list; a wrapped line runs on at the hanging indent); a roman line with no italics opens a
  paragraph whose next italic line stays on a line of its own (a senior member and the school).

A piece's title is its outline name, checked against its printed title (the title-size lines);
a title-size line the name doesn't account for is a subtitle, the text's first paragraph. Every
reference the book links into the Bible is a ``ref:`` link (``notes.link_spans``). Anything a
line can't be read as is an error: nothing is guessed silently.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from emb_convert.clean import Fixes
from emb_convert.documents import (
    MARGIN,
    Blocks,
    Front,
    Witnessed,
    gap,
    hygiene,
    is_title,
    italic_k,
    left,
    md,
    title_agrees,
    title_lines,
    wrapped,
)
from emb_convert.layout import Layout
from emb_convert.lines import Line
from emb_convert.notes import Context, LinkFinding, link_spans
from emb_convert.notetext import Piece, assemble, plain_text, relink
from emb_convert.pdfxml import TextItem
from emb_convert.study import link_runs

KIND = "front-matter"
COPYRIGHT_TITLE = "Copyright"  # our word: the book prints no title on its copyright page
BULLET = "•"
INDENT = 48  # a prose line starting right of the margin up to here opens a paragraph (46)
HANG = 58  # … up to here: a list item's hanging indent (55)
ITEM_RUN = 64  # … up to here: an item's own paragraph running on (61)
ITEM_OPEN = 72  # … up to here: an item's own paragraph opening (69)
SIGNED = 100  # an italic line starting right of this is set right: a signature

Key = tuple[str, int, int]


def slug(number: int) -> str:
    return f"front-matter-{number}"


def key(number: int, section: int) -> Key:
    return (f"FRONT {number} §{section}", 0, 1)


@dataclass(slots=True)
class FrontPiece:
    number: int
    title: str
    reader: str  # copyright · prose · roles · people
    lines: list[Line]  # what it prints, its title aside
    structures: Counter[str] = field(default_factory=Counter[str])
    words: int = 0
    document: dict[str, object] | None = None


@dataclass(slots=True)
class FrontFindings:
    """EMB's front matter (V8-S5c): found, written and checked."""

    pieces: list[FrontPiece] = field(default_factory=list[FrontPiece])
    contents: int = 0  # contents pages set aside
    references: int = 0  # reference sections set aside (the Verse Finder, V8-S6)
    links: list[LinkFinding] = field(default_factory=list[LinkFinding])
    fixes: Counter[str] = field(default_factory=Counter[str])
    bullets: int = 0  # list bullets the Markdown's "- " carries
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])
    witnessed: Witnessed = field(default_factory=Witnessed)

    @property
    def documents(self) -> list[dict[str, object]]:
        return [p.document for p in self.pieces if p.document is not None]

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and not any(self.hygiene.values())
            and all(f.evidence != "unexplained" for f in self.links)
        )


def _all(line: Line, test: Callable[[TextItem], bool]) -> bool:
    return all(test(i) for i in line.nonblank)


def _italic(line: Line) -> bool:
    return _all(line, lambda i: i.italic)


def _roman(line: Line) -> bool:
    return _all(line, lambda i: not i.italic)


def _bold(line: Line) -> bool:
    return _all(line, lambda i: i.bold)


def _label(line: Line) -> bool:
    """A group label: italic capitals at the margin."""
    return left(line) <= MARGIN and _italic(line) and line.text.upper() == line.text


def reader_for(lines: Sequence[Line]) -> str:
    """The reader a piece's layout calls for (its title aside): every line centred, roles; a
    group label at the margin, people; otherwise prose."""
    if lines and all(left(line) > MARGIN for line in lines):
        return "roles"
    if any(_label(line) for line in lines):
        return "people"
    return "prose"


# --- the readers: lines → blocks ---------------------------------------------------------------


@dataclass(slots=True)
class Block:
    kind: str  # head · paragraph · list · signature · roles · senior · label · people
    groups: list[list[Line]] = field(default_factory=list[list[Line]])
    items: list[list[list[Line]]] = field(default_factory=list[list[list[Line]]])  # list items


def read_copyright(lines: Sequence[Line], errors: list[str]) -> list[Block]:
    blocks: list[Block] = []
    before: Line | None = None
    for line in lines:
        if left(line) > MARGIN:
            errors.append(f"FRONT 1 p{line.page} top {line.top}: a line off the margin")
            continue
        new_block = (
            before is None
            or gap(before, line)
            or (before.page != line.page and not wrapped(before))
        )
        if new_block:
            blocks.append(Block("paragraph", [[line]]))
        elif before is not None and wrapped(before):
            blocks[-1].groups[-1].append(line)
        else:
            blocks[-1].groups.append([line])
        before = line
    for block in blocks:
        if len(block.groups) > 1:
            block.kind = "list"
    return blocks


class _Prose:
    def __init__(self, name: str, errors: list[str]) -> None:
        self.name = name
        self.errors = errors
        self.blocks: list[Block] = []
        self.before: Line | None = None
        self.open: list[Line] | None = None  # the paragraph lines run on to
        self.in_item = False  # the open paragraph is a list item's own further paragraph

    def error(self, line: Line, what: str) -> None:
        self.errors.append(f"{self.name} p{line.page} top {line.top}: {what}")

    def close(self) -> None:
        self.open = None

    def line(self, line: Line) -> None:
        at = left(line)
        text = line.text.lstrip()
        before = self.before
        runs_on = before is not None and wrapped(before) and not gap(before, line)
        last = self.blocks[-1] if self.blocks else None
        if at <= MARGIN and _bold(line):
            self.close()
            self.blocks.append(Block("head", [[line]]))
        elif at > SIGNED and _italic(line):
            self.close()
            self.blocks.append(Block("signature", [[line]]))
        elif at <= MARGIN and text.startswith(BULLET):
            if last is None or last.kind != "list":
                self.blocks.append(Block("list"))
                last = self.blocks[-1]
            last.items.append([[line]])
            self.open, self.in_item = last.items[-1][-1], False
        elif MARGIN < at <= HANG and at > INDENT:  # an item's wrap
            if self.open is None or self.in_item or not runs_on or last is None:
                self.error(line, "a line at the hanging indent that continues no item")
                return
            if last.kind != "list":
                self.error(line, "a line at the hanging indent that continues no item")
                return
            self.open.append(line)
        elif ITEM_RUN < at <= ITEM_OPEN:  # an item's own further paragraph opens
            if last is None or last.kind != "list" or runs_on:
                self.error(line, "an item's paragraph that opens inside a paragraph")
                return
            last.items[-1].append([line])
            self.open, self.in_item = last.items[-1][-1], True
        elif HANG < at <= ITEM_RUN:  # … runs on
            if self.open is None or not self.in_item or not runs_on:
                self.error(line, "a line at an item's paragraph indent that continues nothing")
                return
            self.open.append(line)
        elif at <= INDENT:
            self.body(line, at, runs_on, last)
        else:
            self.error(line, f"a line at left {at} the layout doesn't explain")
            return
        self.before = line

    def body(self, line: Line, at: int, runs_on: bool, last: Block | None) -> None:
        before = self.before
        if (
            at <= MARGIN
            and runs_on
            and self.open is not None
            and last is not None
            and last.kind == "paragraph"
        ):
            self.open.append(line)
            return
        opens = (
            at > MARGIN
            or before is None
            or before.page != line.page
            or gap(before, line)
            or (last is not None and last.kind == "head")
        )
        if not opens:
            self.error(line, "a paragraph opening at the margin with nothing to open it")
        self.blocks.append(Block("paragraph", [[line]]))
        self.open, self.in_item = self.blocks[-1].groups[0], False


def read_prose(name: str, lines: Sequence[Line], errors: list[str]) -> list[Block]:
    prose = _Prose(name, errors)
    for line in lines:
        prose.line(line)
    return prose.blocks


def read_roles(name: str, lines: Sequence[Line], errors: list[str]) -> list[Block]:
    blocks: list[Block] = []
    for line in lines:
        if _italic(line):
            last = blocks[-1] if blocks else None
            if last is not None and len(last.groups) == 1:
                last.groups[0].append(line)  # a role wrapped onto the next line
            else:
                blocks.append(Block("roles", [[line]]))
        elif _roman(line) and blocks:
            blocks[-1].groups.append([line])
        else:
            errors.append(f"{name} p{line.page} top {line.top}: a line the roles don't explain")
    for block in blocks:
        if len(block.groups) < 2:
            errors.append(f"{name} p{block.groups[0][0].page}: a role with no name under it")
    return blocks


def read_people(name: str, lines: Sequence[Line], errors: list[str]) -> list[Block]:
    blocks: list[Block] = []
    before: Line | None = None
    for line in lines:
        at = left(line)
        last = blocks[-1] if blocks else None
        if at <= MARGIN and _bold(line):
            blocks.append(Block("head", [[line]]))
        elif _label(line):
            blocks.append(Block("label", [[line]]))
        elif at <= MARGIN and _italic(line):
            if last is None or last.kind != "senior" or len(last.groups) != 1:
                errors.append(f"{name} p{line.page} top {line.top}: an italic line under no one")
            else:
                last.groups.append([line])
        elif at <= MARGIN and _roman(line):
            blocks.append(Block("senior", [[line]]))
        elif at <= MARGIN:
            if last is None or last.kind != "people":
                blocks.append(Block("people"))
                last = blocks[-1]
            last.items.append([[line]])
        elif INDENT < at <= HANG and last is not None and last.kind == "people":
            if before is None or not wrapped(before):
                errors.append(f"{name} p{line.page} top {line.top}: a hanging line under no wrap")
            last.items[-1][-1].append(line)
        else:
            errors.append(f"{name} p{line.page} top {line.top}: a line the list doesn't explain")
        before = line
    return blocks


# --- Markdown ----------------------------------------------------------------------------------


def write(blocks: Sequence[Block], out: Blocks, structures: Counter[str]) -> None:
    for block in blocks:
        structures[block.kind] += 1
        if block.kind == "head":
            out.head(block.groups[0])
        elif block.kind in ("paragraph", "signature", "label"):
            out.paragraph(block.groups[0])
        elif block.kind == "list" and block.items:
            _items(block, out, structures)
        elif block.kind == "list":
            out.items(block.groups)  # the copyright page's one-unit-per-line list
            structures["list items"] += len(block.groups)
        elif block.kind in ("roles", "senior"):
            out.broken([block.groups[0], *([line] for g in block.groups[1:] for line in g)])
            what = "names" if block.kind == "roles" else "senior lines"
            structures[what] += len(block.groups) - 1
        else:  # people
            out.items([item[0] for item in block.items])
            structures["people"] += len(block.items)
            structures["people wrapped"] += sum(1 for item in block.items if len(item[0]) > 1)


def _items(block: Block, out: Blocks, structures: Counter[str]) -> None:
    """A bulleted list: each item's first paragraph after "- ", its own further paragraphs
    indented under it (a loose item)."""
    entries: list[str] = []
    plains: list[str] = []
    for item in block.items:
        first = out.text(item[0], strip=BULLET)
        parts = [f"- {md(first)}"]
        texts = [first.plain]
        for paragraph in item[1:]:
            t = out.text(paragraph)
            parts.append(f"  {md(t)}")
            texts.append(t.plain)
            structures["item paragraphs"] += 1
        entries.append("\n\n".join(parts))
        plains.append("\n\n".join(texts))
    out.add("\n".join(entries), "\n".join(plains))
    structures["list items"] += len(block.items)


# --- the run -----------------------------------------------------------------------------------


def build_front(front: Front, layout: Layout, ctx: Context) -> FrontFindings:
    """The front matter's pieces → documents, with their links, checks and EPUB texts."""
    found = FrontFindings(contents=len(front.contents), references=len(front.references))
    found.errors += front.errors
    pieces = [FrontPiece(1, COPYRIGHT_TITLE, "copyright", list(front.copyright))]
    for n, section in enumerate(front.pieces, 2):
        taken, subtitle = title_lines(section)
        if not title_agrees(section, taken):
            found.errors.append(
                f"FRONT {n} p{section.start}: its printed title isn't its outline name"
            )
        body = [line for line in section.lines if not is_title(line)]
        piece = FrontPiece(n, section.title, reader_for(body), [*subtitle, *body])
        piece.structures["subtitle"] = len(subtitle)
        pieces.append(piece)
    for piece in pieces:
        _piece(found, piece, layout, ctx)
        found.pieces.append(piece)
    if len(pieces) != 5:
        found.errors.append(f"FRONT: {len(pieces)} pieces, not 5")
    return found


def _piece(found: FrontFindings, piece: FrontPiece, layout: Layout, ctx: Context) -> None:
    name = f"FRONT {piece.number}"
    if not piece.lines:
        found.errors.append(f"{name}: nothing printed")
        return

    def is_link(item: TextItem) -> bool:
        page = item.link_page
        return page is None or layout.bible_start <= page < layout.notes_start

    run_of, runs = link_runs(piece.lines, is_link)

    def inline(lines: Sequence[Line]) -> list[Piece]:
        pieces = assemble(
            lines, ctx.vocabulary, Fixes(), found.fixes, repair=ctx.repair, run_of=run_of, bold=True
        )
        return italic_k(pieces, ctx.vocabulary, Fixes(), found.fixes)

    scratch: Counter[str] = Counter()

    def quiet(lines: Sequence[Line], fixes: Fixes) -> list[Piece]:
        pieces = assemble(
            lines, ctx.vocabulary, fixes, scratch, repair=ctx.repair, run_of=run_of, bold=True
        )
        return italic_k(pieces, ctx.vocabulary, fixes, scratch)

    flat = quiet(piece.lines, Fixes())
    spans = link_spans(
        found.links, found.errors, "", name, flat, runs, (0, 0), ctx, reviewed=frozenset()
    )
    out = Blocks(inline, lambda pieces: relink(pieces, spans))
    errors: list[str] = []
    subtitle = piece.structures["subtitle"]
    head = piece.lines[:subtitle]
    rest = piece.lines[subtitle:]
    if head:
        out.paragraph(head)
    if piece.reader == "copyright":
        blocks = read_copyright(rest, errors)
    elif piece.reader == "prose":
        blocks = read_prose(name, rest, errors)
    elif piece.reader == "roles":
        blocks = read_roles(name, rest, errors)
    else:
        blocks = read_people(name, rest, errors)
    found.errors += errors
    write(blocks, out, piece.structures)
    found.bullets += piece.structures["list items"] if piece.reader == "prose" else 0
    if not out.holds([p for p in flat if p.text]):
        found.errors.append(f"{name}: its blocks don't hold exactly the text it prints")
    hygiene(found.hygiene, name, out.text_plain, piece.lines, ctx, out.problems)
    piece.words = len(out.text_plain.split())
    piece.document = {
        "slug": slug(piece.number),
        "kind": KIND,
        "title": piece.title,
        "ordinal": piece.number,
        "text": out.document,
    }
    for n, lines in enumerate(sections(piece, blocks), 1):
        found.witnessed.add(
            key(piece.number, n),
            lines,
            lambda fixes, lines=lines: plain_text(quiet(lines, fixes)),
        )


def sections(piece: FrontPiece, blocks: Sequence[Block]) -> list[list[Line]]:
    """The piece's lines split where a head opens a section; a subtitle alone runs on into the
    first head's section."""
    out: list[list[Line]] = [list(piece.lines[: piece.structures["subtitle"]])]
    for block in blocks:
        lines = [line for group in block.groups for line in group] + [
            line for item in block.items for paragraph in item for line in paragraph
        ]
        if block.kind == "head" and (out[-1] and not _only_subtitle(out, piece)):
            out.append([])
        out[-1] += lines
    return [s for s in out if s]


def _only_subtitle(out: list[list[Line]], piece: FrontPiece) -> bool:
    subtitle = piece.structures["subtitle"]
    return len(out) == 1 and subtitle > 0 and len(out[0]) == subtitle
