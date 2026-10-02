"""An article's body → Markdown blocks (V8-S3a; docs/v8/SPEC.md §4.2).

The articles print their structure in indentation, weight and spacing (measured on the PDF):

- a paragraph opens indented (left 46) and wraps to the margin (38); its opening words may be
  bold capitals (a lead-in, kept bold as printed);
- a set-off block sits at 61: a quotation (a paragraph inside it opens at 69), a list with
  hanging items (an item opens at 61 or 69 and wraps to 79), or a list printed one short item
  per line. The book prints no bullet glyph; a list becomes Markdown's ``- `` list;
- a numbered list: "1." opens an item at 46 (or 38 after a paragraph's end); its lead wraps to
  38, and its own paragraphs follow at 78 (wrapping to 61);
- verse quoted line by line: italic lines at 46 that don't reach the margin — a block quote
  with hard line breaks;
- Someone You Should Know opens with a two-size bold headline and a set-off summary, may carry
  bold-italic subheads, ends with a bold closing line, and three articles end with a source
  note in size 9, called out by a superscript number;
- Personal Gold opens with an italic epigraph, set off.

Inline text is S2b's note text (``notetext``: broken words, small caps, escapes, ``ref:``
links) plus bold. Everything else a line can be is an error, so nothing is guessed silently.
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from emb_convert.lines import Line
from emb_convert.notetext import NoteText, Piece, emphasis_ok, plain_of, render
from emb_convert.pdfxml import TextItem

WRAP_RIGHT = 330  # a line reaching this x ran to the right margin
GAP = 20  # more than a line's pitch (14–15 points): a set-off block's space above or below
HEADLINE_SIZE = 23
FOOTNOTE_SIZE = 9
MARKER_SIZE = 7
SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")

_NUMBER = re.compile(r"^\s*(\d+)\s?\.\s+\S")
_NUMBER_PREFIX = re.compile(r"^\s*\d+\s?\.\s*")
_OPENING_GAP = re.compile(r"([(\[“‘]) (?=\w)")  # a source note's "“ X" (its size-9 line)
_WS = re.compile(r"\s+")


class Kind(Enum):
    HEADLINE = "headline"
    SUBHEAD = "subhead"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    POETRY = "poetry"
    LIST = "list"
    NUMBERED = "numbered list"
    FOOTNOTE = "source note"
    CLOSING = "closing line"


@dataclass(slots=True)
class Block:
    kind: Kind
    groups: list[list[Line]]  # its paragraphs, items or lines (one group for the rest)
    numbers: list[int] = field(default_factory=list[int])  # a numbered list's numbers
    bodies: list[list[list[Line]]] = field(default_factory=list[list[list[Line]]])


@dataclass(slots=True)
class Layout:
    """How one article is built, for the summary."""

    blocks: list[Block] = field(default_factory=list[Block])
    lead_in: bool = False
    errors: list[str] = field(default_factory=list[str])


def _left(line: Line) -> int:
    return min(i.left for i in line.nonblank)


def _band(line: Line) -> str:
    left = _left(line)
    if left <= 41:
        return "body"
    if left <= 52:
        return "indent"
    if left <= 64:
        return "block"
    if left <= 73:
        return "block-indent"
    if left <= 84:
        return "deep"
    return "center"


def _wrapped(line: Line) -> bool:
    return line.right >= WRAP_RIGHT


def _gap(before: Line | None, line: Line) -> bool:
    return before is not None and before.page == line.page and line.top - before.top > GAP


def _all_bold(line: Line) -> bool:
    return all(i.bold for i in line.nonblank)


def _poem_line(line: Line) -> bool:
    return _band(line) == "indent" and all(i.italic for i in line.nonblank) and not _wrapped(line)


def _footnote_line(line: Line) -> bool:
    return any(i.size == FOOTNOTE_SIZE for i in line.nonblank)


def _text(lines: Sequence[Line]) -> str:
    return " ".join(" ".join(line.text for line in lines).split())


def superscript_markers(lines: list[Line], is_note_marker: Callable[[TextItem], bool]) -> int:
    """A source note's number (size 7, blue, linking within the features) becomes a
    superscript digit, in the text and at the note; returns how many."""
    count = 0
    for line in lines:
        for n, item in enumerate(line.items):
            if is_note_marker(item):
                line.items[n] = dataclasses.replace(
                    item,
                    text=item.stripped.translate(SUPERSCRIPT),
                    size=12,
                    blue=False,
                    bold=False,
                    link_page=None,
                )
                count += 1
    return count


def segment(lines: list[Line], *, opening_quote: bool) -> Layout:
    """Body lines → blocks. ``opening_quote``: the first set-off block is the article's
    summary or epigraph, always a quotation."""
    layout = Layout()
    n = len(lines)
    start, end = 0, n
    j = 0
    while j < n and _all_bold(lines[j]):
        j += 1
    if j and any(i.size == HEADLINE_SIZE for line in lines[:j] for i in line.nonblank):
        layout.blocks.append(Block(Kind.HEADLINE, [lines[:j]]))
        start = j
    k = n
    while k > start and _all_bold(lines[k - 1]):
        k -= 1
    closing = [Block(Kind.CLOSING, [lines[k:n]])] if k < n else []
    end = k
    f = end
    while f > start and _footnote_line(lines[f - 1]):
        f -= 1
    notes = _footnotes(lines[f:end])
    end = f
    _middle(lines[start:end], layout, opening_quote=opening_quote)
    layout.blocks += notes + closing
    first = next((b for b in layout.blocks if b.kind is Kind.PARAGRAPH), None)
    if first is not None:
        items = first.groups[0][0].nonblank
        layout.lead_in = bool(items) and items[0].bold
    return layout


def _footnotes(lines: list[Line]) -> list[Block]:
    blocks: list[Block] = []
    for line in lines:
        if (
            not blocks
            or line.nonblank[0].size == MARKER_SIZE
            or line.nonblank[0].text[:1] in ("¹²³⁴⁵⁶⁷⁸⁹")
        ):
            blocks.append(Block(Kind.FOOTNOTE, [[line]]))
        else:
            blocks[-1].groups[0].append(line)
    return blocks


def _middle(lines: list[Line], layout: Layout, *, opening_quote: bool) -> None:
    blocks = layout.blocks
    i = 0
    quoted = not opening_quote  # True once the opening summary/epigraph is placed
    while i < len(lines):
        line = lines[i]
        before = lines[i - 1] if i else None
        band = _band(line)
        gap = _gap(before, line)
        last = blocks[-1] if blocks else None
        number = _NUMBER.match(line.text)
        expected = last.numbers[-1] + 1 if last is not None and last.kind is Kind.NUMBERED else 1
        if (
            number
            and int(number.group(1)) == expected
            and (
                band == "indent"
                or (band == "body" and (before is None or not _wrapped(before) or gap))
            )
        ):
            i = _numbered(lines, i, int(number.group(1)), blocks)
            continue
        if band in ("block", "block-indent", "deep"):
            run = [line]
            i += 1
            while (
                i < len(lines)
                and _band(lines[i]) in ("block", "block-indent", "deep")
                and not _gap(lines[i - 1], lines[i])
            ):
                run.append(lines[i])
                i += 1
            blocks.append(_set_off(run, force_quote=not quoted, layout=layout))
            quoted = True
            continue
        quoted = True
        if _poem_line(line):
            run = [line]
            k = i + 1
            while k < len(lines) and _poem_line(lines[k]) and not _gap(lines[k - 1], lines[k]):
                run.append(lines[k])
                k += 1
            if len(run) >= 2:
                blocks.append(Block(Kind.POETRY, [run]))
                i = k
                continue
        if band == "body" and _all_bold(line) and i:
            run = [line]
            k = i + 1
            while k < len(lines) and _all_bold(lines[k]) and _wrapped(lines[k - 1]):
                run.append(lines[k])
                k += 1
            if not _wrapped(run[-1]):  # a heading line of its own, not a bold lead-in
                blocks.append(Block(Kind.SUBHEAD, [run]))
                i = k
                continue
        if band == "indent":
            blocks.append(Block(Kind.PARAGRAPH, [[line]]))
        elif band == "body":
            if (
                last is not None
                and last.kind is Kind.PARAGRAPH
                and before is not None
                and last.groups[-1][-1] is before
                and _wrapped(before)
                and not gap
            ):
                last.groups[-1].append(line)
            else:
                blocks.append(Block(Kind.PARAGRAPH, [[line]]))
        else:
            layout.errors.append(f"p{line.page} top {line.top}: a line at left {_left(line)}")
        i += 1


def _numbered(lines: list[Line], i: int, number: int, blocks: list[Block]) -> int:
    lead = [lines[i]]
    i += 1
    while (
        i < len(lines)
        and _band(lines[i]) == "body"
        and _wrapped(lines[i - 1])
        and not _gap(lines[i - 1], lines[i])
    ):
        lead.append(lines[i])
        i += 1
    body: list[list[Line]] = []
    while i < len(lines) and _band(lines[i]) in ("deep", "block"):
        if _band(lines[i]) == "deep" or not body:
            body.append([lines[i]])
        else:
            body[-1].append(lines[i])
        i += 1
    last = blocks[-1] if blocks else None
    if last is None or last.kind is not Kind.NUMBERED or number == 1:
        last = Block(Kind.NUMBERED, [])
        blocks.append(last)
    last.groups.append(lead)
    last.numbers.append(number)
    last.bodies.append(body)
    return i


def _set_off(run: list[Line], *, force_quote: bool, layout: Layout) -> Block:
    bands = [_band(line) for line in run]
    if not force_quote and "deep" in bands and bands[0] in ("block", "block-indent"):
        items: list[list[Line]] = []
        for k, (line, band) in enumerate(zip(run, bands, strict=True)):
            new = band == "block-indent" or (
                band == "block" and (bands[k - 1] == "deep" or not _wrapped(run[k - 1]))
            )
            if not items or new:
                items.append([line])
            else:
                items[-1].append(line)
        return Block(Kind.LIST, items)
    if (
        not force_quote
        and len(run) >= 2
        and all(b == "block" for b in bands)
        and not any(_wrapped(line) for line in run)
    ):
        return Block(Kind.LIST, [[line] for line in run])
    paragraphs: list[list[Line]] = []
    for k, (line, band) in enumerate(zip(run, bands, strict=True)):
        if band == "deep":
            layout.errors.append(f"p{line.page} top {line.top}: a hanging line in a quotation")
        if not paragraphs or band == "block-indent" or not _wrapped(run[k - 1]):
            paragraphs.append([line])
        else:
            paragraphs[-1].append(line)
    return Block(Kind.QUOTE, paragraphs)


# --- Markdown ------------------------------------------------------------------------------

Inline = Callable[[Sequence[Line]], list[Piece]]


@dataclass(slots=True)
class ArticleText:
    markdown: str
    plain: str  # the text as read, blocks apart by blank lines (hygiene runs on it)
    printed: str  # every character the body prints, spaces aside (the consistency check)
    problems: list[str] = field(default_factory=list[str])
    gaps_closed: int = 0


def _close_gaps(pieces: list[Piece]) -> tuple[list[Piece], int]:
    out: list[Piece] = []
    count = 0
    for piece in pieces:
        text, n = _OPENING_GAP.subn(r"\1", piece.text)
        count += n
        out.append(dataclasses.replace(piece, text=text))
    return out, count


def write(
    layout: Layout,
    inline: Inline,
    relink: Callable[[list[Piece]], tuple[list[Piece], list[str]]],
    byline: str = "",
) -> ArticleText:
    """The blocks as Markdown. ``inline`` assembles lines into pieces; ``relink`` turns their
    link runs into ``ref:`` targets."""
    result = ArticleText("", "", "")
    markdown: list[str] = []
    plain: list[str] = []
    printed: list[str] = []

    def text(
        lines: Sequence[Line],
        strip_number: bool = False,
        heading: bool = False,
        note: bool = False,
    ) -> NoteText:
        pieces = inline(lines)
        if note:  # the size-9 source line's "“ X": the rendered page prints none
            pieces, closed = _close_gaps(pieces)
            result.gaps_closed += closed
        printed.append(" ".join(p.text for p in pieces))
        if strip_number:
            pieces = _strip_number(pieces)
        if heading:  # a heading is bold already; its weight and slant stay out of the Markdown
            pieces = [dataclasses.replace(p, bold=False, italic=False) for p in pieces]
        pieces, targets = relink(pieces)
        rendered = render(pieces, targets, always=True)
        assert rendered.markdown is not None
        if not emphasis_ok(rendered.markdown):
            result.problems.append("emphasis-flanking")
        if plain_of(rendered.markdown) != rendered.plain:
            result.problems.append("markdown-round-trip")
        return rendered

    if byline:
        markdown.append(f"*from* {byline}")
        plain.append(f"from {byline}")
    for block in layout.blocks:
        kind = block.kind
        if kind in (Kind.HEADLINE, Kind.SUBHEAD):
            t = text(block.groups[0], heading=True)
            markdown.append(("## " if kind is Kind.HEADLINE else "### ") + _md(t))
            plain.append(t.plain)
        elif kind in (Kind.PARAGRAPH, Kind.CLOSING, Kind.FOOTNOTE):
            t = text(block.groups[0], note=kind is Kind.FOOTNOTE)
            markdown.append(_md(t))
            plain.append(t.plain)
        elif kind is Kind.QUOTE:
            ts = [text(group) for group in block.groups]
            markdown.append("\n>\n".join(f"> {_md(t)}" for t in ts))
            plain.append("\n\n".join(t.plain for t in ts))
        elif kind is Kind.POETRY:
            ts = [text([line]) for line in block.groups[0]]
            markdown.append("\\\n".join(f"> {_md(t)}" for t in ts))
            plain.append("\n".join(t.plain for t in ts))
        elif kind is Kind.LIST:
            ts = [text(group) for group in block.groups]
            markdown.append("\n".join(f"- {_md(t)}" for t in ts))
            plain.append("\n".join(t.plain for t in ts))
        else:
            items: list[str] = []
            for number, lead, body in zip(block.numbers, block.groups, block.bodies, strict=True):
                t = text(lead, strip_number=True)
                parts = [f"{number}. {_md(t)}"]
                plain.append(f"{number}. {t.plain}")
                for paragraph in body:
                    b = text(paragraph)
                    parts.append(f"   {_md(b)}")
                    plain.append(b.plain)
                items.append("\n\n".join(parts))
            loose = any(block.bodies)
            markdown.append(("\n\n" if loose else "\n").join(items))
    result.markdown = "\n\n".join(markdown)
    result.plain = "\n\n".join(plain)
    result.printed = _WS.sub("", " ".join(printed))
    return result


def _md(text: NoteText) -> str:
    assert text.markdown is not None
    return text.markdown


def _strip_number(pieces: list[Piece]) -> list[Piece]:
    """A numbered item's lead without its printed number ("2 . " included)."""
    joined = "".join(p.text for p in pieces)
    match = _NUMBER_PREFIX.match(joined)
    cut = match.end() if match else 0
    out: list[Piece] = []
    for piece in pieces:
        if cut >= len(piece.text):
            cut -= len(piece.text)
            continue
        out.append(dataclasses.replace(piece, text=piece.text[cut:]))
        cut = 0
    return out


def structures(layout: Layout) -> Counter[str]:
    """What the article prints, by kind (items and paragraphs counted inside their block)."""
    counts: Counter[str] = Counter()
    for block in layout.blocks:
        counts[block.kind.value] += 1
        if block.kind is Kind.LIST:
            counts["list items"] += len(block.groups)
        if block.kind is Kind.NUMBERED:
            counts["numbered items"] += len(block.groups)
            counts["numbered items with paragraphs"] += sum(1 for b in block.bodies if b)
        if block.kind is Kind.QUOTE:
            counts["quoted paragraphs"] += len(block.groups)
        if block.kind is Kind.POETRY:
            counts["quoted lines"] += len(block.groups[0])
    if layout.lead_in:
        counts["lead-in capitals"] += 1
    return counts


def text_of(lines: Sequence[Line]) -> str:
    return _text(lines)
