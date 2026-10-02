"""One note's PDF items → its plain text and, when it needs it, Markdown (V8-S2b).

Shared by the textual and the study notes (docs/v8/SPEC.md §4.2, ADR-0011). Note text gets
the verse text's fixes (``clean.py``): broken words joined, small caps glued, wrapped hyphens
and dashes closed up, fractions, fused compounds repaired. Then:

- italic runs become ``*…*``, with any whitespace or punctuation at a run's edge moved outside
  the delimiters, so every ``*`` opens or closes by CommonMark's flanking rules;
- the book's own CommonMark specials ("[2 units]") are escaped with ``\\``;
- links become ``[display](ref:TARGET)`` (ADR-0011's grammar; study notes only).

A note with no italics and no links stays plain text: no escapes, no ``text_format``. Two
checks guard every Markdown note: ``emphasis_ok`` (every ``*`` flanks correctly) and
``plain_of`` (the Markdown stripped back equals the plain text exactly).
"""

from __future__ import annotations

import re
import string
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from emb_convert.clean import CompoundRepair, Fixes, Vocabulary, fraction, line_joiner, unspace
from emb_convert.lines import Line
from emb_convert.pdfxml import TextItem

SMALL_SIZE = 7  # small caps, small digits (a verse number quoted in a note), superscripts
WRAP_RIGHT = 330  # a line reaching this x ran to the right margin (justified prose)
EN_DASH = "–"

_WS = re.compile(r"\s+")
_SPECIAL = re.compile(r"([\\`*_\[\]<~])")
_ENTITY = re.compile(r"&(?=#?[0-9A-Za-z]+;)")
_BLOCK_START = re.compile(r"^(?:[>]|#+(?= |$)|[-+](?= |$))")
_ORDERED_START = re.compile(r"^(\d+)([.)])(?= |$)")
_ASCII_PUNCT = frozenset(string.punctuation)


@dataclass(frozen=True, slots=True)
class Piece:
    """A stretch of note text with one style: italic or not, inside a link run or not."""

    text: str
    italic: bool = False
    run: int | None = None


@dataclass(frozen=True, slots=True)
class NoteText:
    plain: str
    markdown: str | None  # None: the note needs no Markdown (stored as plain text)


# --- assembly ------------------------------------------------------------------------------


def _is_small_caps(item: TextItem) -> bool:
    text = item.stripped
    return (
        item.size == SMALL_SIZE
        and not item.blue
        and any(c.isalpha() for c in text)
        and text == text.upper()
        and not item.text[:1].isspace()
    )


def _line_pieces(
    line: Line,
    items: list[TextItem],
    vocabulary: Vocabulary,
    fixes: Fixes,
    counts: Counter[str],
    repair: CompoundRepair | None,
    run_of: Mapping[int, int],
) -> list[Piece]:
    first_content = next((i for i in line.items if i.stripped), None)
    justified = line.right >= WRAP_RIGHT
    pieces: list[Piece] = []
    k = 0
    while k < len(items):
        item = items[k]
        nxt = items[k + 1] if k + 1 < len(items) else None
        text = item.text
        if (
            item.size == SMALL_SIZE
            and item.stripped.isdigit()
            and nxt is not None
            and nxt.size == SMALL_SIZE
            and nxt.stripped == "/"
        ):
            den = items[k + 2].stripped if k + 2 < len(items) else ""
            pieces.append(Piece(fraction(item.stripped, den, fixed=fixes.fractions), item.italic))
            counts["fractions"] += 1
            k += 3
            continue
        if item.size == SMALL_SIZE and item.stripped.isdigit():
            text = f" {item.stripped} "  # a verse number inside a quoted reading: its own word
        elif fixes.letter_spacing:
            # in a note, a justified line breaks words anywhere ("ri ver", "moun tains"),
            # not only where the verse text does. A split just after an apostrophe is the
            # book's own ("Name’ s": the rendered page and the EPUB both print it)
            fixed = unspace(
                text,
                vocabulary,
                italic=item.italic,
                first=item is first_content,
                justified=justified,
                glued=nxt is not None and _is_small_caps(nxt),
                anywhere=justified,
                apostrophe_splits=False,
                k_breaks=item.italic,
            )
            if fixed is not None:
                counts["letter-spaced"] += 1
                text = fixed
        if repair is not None and fixes.compound_hyphens:
            text, repaired = repair.repair(text)
            counts["compound-hyphens"] += repaired
        pieces.append(Piece(text, item.italic, run_of.get(id(item))))
        k += 1
    return pieces


def join_lines(left: str, right: str, fixes: Fixes, *, wrapped: bool) -> str:
    """``clean.line_joiner``, plus: an en dash ending a wrapped line before a digit closes up
    (a reference range, "4:14–" / "10:39")."""
    if (
        wrapped
        and fixes.line_hyphens
        and left.rstrip().endswith(EN_DASH)
        and right.lstrip()[:1].isdigit()
    ):
        return ""
    return line_joiner(left, right, fixes, wrapped=wrapped)


def assemble(
    lines: Sequence[Line],
    vocabulary: Vocabulary,
    fixes: Fixes,
    counts: Counter[str],
    *,
    repair: CompoundRepair | None = None,
    skip: frozenset[int] = frozenset(),
    run_of: Mapping[int, int] | None = None,
    keep_spaces: bool = False,
) -> list[Piece]:
    """The pieces of a note's text, line by line. ``skip``: ids of items that aren't text (a
    note's label); ``run_of``: item id → the link run it belongs to (study notes);
    ``keep_spaces``: leave the PDF's spacing as printed — a double space is a justification
    gap, so a real word gap — with a line break as a double space (the broken-word check)."""
    runs: Mapping[int, int] = run_of or {}
    pieces: list[Piece] = []
    previous: Line | None = None
    for line in lines:
        items = [i for i in line.items if id(i) not in skip]
        if not any(i.stripped for i in items):
            continue
        new = _line_pieces(line, items, vocabulary, fixes, counts, repair, runs)
        if previous is not None and pieces:
            tail = "".join(p.text for p in pieces)
            head = "".join(p.text for p in new)
            joiner = join_lines(tail, head, fixes, wrapped=previous.right >= WRAP_RIGHT)
            if keep_spaces and joiner == " ":
                joiner = "  "
            pieces, new = _rstrip(pieces), _lstrip(new)
            left = next((p for p in reversed(pieces) if p.text), Piece(""))
            right = next((p for p in new if p.text), Piece(""))
            pieces.append(
                Piece(
                    joiner,
                    left.italic and right.italic,
                    left.run if left.run is not None and left.run == right.run else None,
                )
            )
        pieces.extend(new)
        previous = line
    return normalize(pieces, collapse=not keep_spaces)


def _rstrip(pieces: list[Piece]) -> list[Piece]:
    out = list(pieces)
    while out and not out[-1].text.strip():
        out.pop()
    if out:
        out[-1] = replace(out[-1], text=out[-1].text.rstrip())
    return out


def _lstrip(pieces: list[Piece]) -> list[Piece]:
    out = list(pieces)
    while out and not out[0].text.strip():
        out.pop(0)
    if out:
        out[0] = replace(out[0], text=out[0].text.lstrip())
    return out


def normalize(pieces: list[Piece], *, collapse: bool = True) -> list[Piece]:
    """Collapse whitespace across pieces, give a gap the style of the text on both sides of
    it, trim the ends and merge neighbours of the same style."""
    collapsed = [replace(p, text=_WS.sub(" ", p.text) if collapse else p.text) for p in pieces]
    collapsed = [p for p in collapsed if p.text]
    styled: list[Piece] = []
    for n, piece in enumerate(collapsed):
        if not piece.text.strip():
            left = next((p for p in reversed(collapsed[:n]) if p.text.strip()), None)
            right = next((p for p in collapsed[n + 1 :] if p.text.strip()), None)
            if left is not None and right is not None:
                piece = Piece(
                    piece.text,
                    left.italic and right.italic,
                    left.run if left.run is not None and left.run == right.run else None,
                )
        styled.append(piece)
    out: list[Piece] = []
    for piece in styled:
        text = piece.text
        if collapse and (not out or out[-1].text.endswith(" ")) and text.startswith(" "):
            text = text[1:]
        if not text:
            continue
        if out and (out[-1].italic, out[-1].run) == (piece.italic, piece.run):
            out[-1] = replace(out[-1], text=out[-1].text + text)
        else:
            out.append(replace(piece, text=text))
    out = _lstrip(_rstrip(out))
    return [p for p in out if p.text]


def plain_text(pieces: Sequence[Piece]) -> str:
    return "".join(p.text for p in pieces)


# --- links ---------------------------------------------------------------------------------


def run_texts(pieces: Sequence[Piece]) -> dict[int, str]:
    """Each link run's text as assembled (wrapped lines joined)."""
    texts: dict[int, str] = {}
    for piece in pieces:
        if piece.run is not None:
            texts[piece.run] = texts.get(piece.run, "") + piece.text
    return texts


def relink(
    pieces: Sequence[Piece], spans: Mapping[int, list[tuple[int, int, str]]]
) -> tuple[list[Piece], list[str]]:
    """Split each link run into its references.

    ``spans``: run → ``(start, end, target)`` slices of the run's text, one per reference.
    Text between them (", ") becomes plain. Returns the new pieces, whose ``run`` indexes
    the returned target list.
    """
    out: list[Piece] = []
    targets: list[str] = []
    texts = run_texts(pieces)
    done: set[int] = set()
    for piece in pieces:
        if piece.run is None:
            out.append(piece)
            continue
        if piece.run in done:
            continue
        done.add(piece.run)
        text = texts[piece.run]
        at = 0
        for start, end, target in spans[piece.run]:
            if start > at:
                out.append(Piece(text[at:start]))
            out.append(Piece(text[start:end], run=len(targets)))
            targets.append(target)
            at = end
        if at < len(text):
            out.append(Piece(text[at:]))
    return normalize(out), targets


# --- Markdown ------------------------------------------------------------------------------


def escape(text: str) -> str:
    """The book's own CommonMark specials, escaped (inline)."""
    return _ENTITY.sub(r"\\&", _SPECIAL.sub(r"\\\1", text))


def _edges(text: str) -> tuple[str, str, str]:
    """Split an italic run into leading and trailing non-alphanumerics and its core."""
    start = 0
    while start < len(text) and not text[start].isalnum():
        start += 1
    end = len(text)
    while end > start and not text[end - 1].isalnum():
        end -= 1
    return text[:start], text[start:end], text[end:]


def render(pieces: Sequence[Piece], targets: Sequence[str] = ()) -> NoteText:
    """Plain text, and Markdown when the note has italics or links."""
    parts: list[str] = []
    needs = False
    for piece in pieces:
        if piece.run is not None:
            parts.append(f"[{escape(piece.text)}](ref:{targets[piece.run]})")
            needs = True
        elif piece.italic:
            lead, core, trail = _edges(piece.text)
            if core:
                parts.append(f"{escape(lead)}*{escape(core)}*{escape(trail)}")
                needs = True
            else:
                parts.append(escape(piece.text))
        else:
            parts.append(escape(piece.text))
    plain = plain_text(pieces)
    if not needs:
        return NoteText(plain, None)
    markdown = "".join(parts)
    markdown = _BLOCK_START.sub(lambda m: "\\" + m.group(0), markdown, count=1)
    markdown = _ORDERED_START.sub(lambda m: f"{m.group(1)}\\{m.group(2)}", markdown, count=1)
    return NoteText(plain, markdown)


def plain_of(markdown: str) -> str:
    """Our Markdown stripped back to text: escapes undone, ``*`` and link syntax dropped."""
    out: list[str] = []
    i = 0
    while i < len(markdown):
        c = markdown[i]
        if c == "\\" and i + 1 < len(markdown) and markdown[i + 1] in _ASCII_PUNCT:
            out.append(markdown[i + 1])
            i += 2
        elif c in "*[":
            i += 1
        elif c == "]" and markdown.startswith("](ref:", i):
            i = markdown.index(")", i) + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _space(c: str) -> bool:
    return c.isspace()


def _punctuation(c: str) -> bool:
    return unicodedata.category(c)[0] in "PS"


def emphasis_ok(markdown: str) -> bool:
    """Every unescaped ``*`` pairs up, each opener left-flanking and each closer right-flanking
    (CommonMark 0.31 §6.2)."""
    delimiters: list[int] = []
    i = 0
    while i < len(markdown):
        if markdown[i] == "\\":
            i += 2
            continue
        if markdown[i] == "*":
            delimiters.append(i)
        i += 1
    if len(delimiters) % 2:
        return False
    for n, at in enumerate(delimiters):
        before = markdown[at - 1] if at else " "
        after = markdown[at + 1] if at + 1 < len(markdown) else " "
        if n % 2 == 0:
            ok = not _space(after) and (
                not _punctuation(after) or _space(before) or _punctuation(before)
            )
        else:
            ok = not _space(before) and (
                not _punctuation(before) or _space(after) or _punctuation(after)
            )
        if not ok:
            return False
    return True
