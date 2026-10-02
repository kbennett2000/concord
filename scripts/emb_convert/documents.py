"""The rest of EMB's documents (V8-S5c; docs/v8/SPEC.md §4.3, ADR-0012): where they stand in
the book, and what the front matter, the reading plan and the Personal Gold authors share.

- **Where.** The front of the book (before ``layout.bible_start``) holds the copyright page (the
  first page with a "copyright ©"), the contents (the pages after it whose every line is a link,
  bar a title and group labels) and one section per outline entry, running to the next entry.
  A section is told by its links alone: one whose every line but its title is a link is the
  reading plan; one where most lines carry a link is a reference section (the Verse Finder,
  V8-S6's); any other is a front-matter piece.
- **Writing.** ``Blocks`` turns a document's blocks into Markdown: inline text by the notes'
  rules (``notetext``), with S5b's checks — emphasis flanking, the Markdown round trip, and the
  blocks holding exactly the text the document prints.
- **The EPUB witness.** ``Witnessed`` keeps each keyed part's text (fixed, raw, one fix alone),
  pages and opening and closing words, in the book's order. ``epub_cut`` cuts the EPUB, read as
  one run of text, at each part's opening and ends it at its closing words. A part whose opening
  the EPUB lost is missing there, and the part before it, which runs on, is marked damaged.

Nothing here holds book text: it is read from the operator's PDF at run time.
"""

from __future__ import annotations

import bisect
import dataclasses
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from emb_convert.clean import Fixes, Vocabulary
from emb_convert.crosscheck import CrossCheck, cross_check_notes
from emb_convert.epub import BREAK
from emb_convert.layout import Layout
from emb_convert.lines import Line, group_lines
from emb_convert.notes import HYGIENE, Context, broken_words, spaced
from emb_convert.notetext import NoteText, Piece, emphasis_ok, plain_of, render
from emb_convert.pdfxml import PdfDocument, TextItem

Key = tuple[str, int, int]

TITLE_SIZE = 15  # a front piece's printed title, the plan's, the Personal Gold index's
MARGIN = 41  # a line starting at or left of this starts at the margin (38)
WRAP_RIGHT = 330  # a line reaching this x ran to the right margin
GAP = 20  # more than a line's pitch (11–15 points)
OPEN_WORDS = 5  # words that find a part in the EPUB, at each end

RESERVED = re.compile(r"copyright ©", re.IGNORECASE)
# a web or e-mail address the book prints ("www.x.com", "x.com", "x@y.com"): its marks run
# into its words by nature, so the punctuation-spacing checks read it as one word
ADDRESS = re.compile(r"\b(?:[\w.-]+@)?(?:[\w-]+\.)+(?:com|org|net|edu)\b")
_LETTERS = re.compile(r"[^a-z0-9]")
# a word the italic font broke right after a "k", on a line that isn't justified
_K_BREAK = re.compile(r"(?<![\w’'])([A-Za-z]*k) ([a-z]+)\b")
_WS = re.compile(r"\s+")
_TOKENS = re.compile(r"\w+|[^\w\s]")
_WS_ALL = re.compile(r"\s+")


def letters(text: str) -> str:
    """A text's letters and digits, lower case: how a printed title meets its outline name."""
    return _LETTERS.sub("", text.casefold())


def nonblank(line: Line) -> list[TextItem]:
    return line.nonblank


def left(line: Line) -> int:
    return min(i.left for i in line.nonblank)


def wrapped(line: Line) -> bool:
    return line.right >= WRAP_RIGHT


def gap(before: Line | None, line: Line) -> bool:
    return before is not None and before.page == line.page and line.top - before.top > GAP


def is_title(line: Line) -> bool:
    return all(i.size == TITLE_SIZE for i in line.nonblank)


def is_link_line(line: Line) -> bool:
    return all(i.blue for i in line.nonblank)


def carries_link(line: Line) -> bool:
    return any(i.blue for i in line.nonblank)


# --- where ---------------------------------------------------------------------------------


def copyright_page(doc: PdfDocument, layout: Layout) -> int | None:
    """The first front page that holds a "copyright ©" (the rights lines' page, V8-S1)."""
    return next(
        (i.page for i in doc.items if i.page < layout.bible_start and RESERVED.search(i.text)),
        None,
    )


@dataclass(slots=True)
class Section:
    """An outline section of the front: its outline name and its printed lines."""

    title: str
    start: int
    end: int  # exclusive
    lines: list[Line]

    @property
    def body(self) -> list[Line]:
        return [line for line in self.lines if not is_title(line)]


@dataclass(slots=True)
class Front:
    copyright: list[Line] = field(default_factory=list[Line])  # the copyright page's lines
    contents: list[int] = field(default_factory=list[int])  # pages set aside: navigation
    pieces: list[Section] = field(default_factory=list[Section])  # front-matter pieces 2…
    references: list[Section] = field(default_factory=list[Section])  # the Verse Finder
    plan: Section | None = None
    errors: list[str] = field(default_factory=list[str])


def _lines(doc: PdfDocument, first: int, end: int) -> list[Line]:
    return [
        line
        for line in group_lines([i for i in doc.items if first <= i.page < end])
        if line.nonblank
    ]


def _contents_page(lines: list[Line]) -> bool:
    """Every line a link, bar a title and the group labels (italic) between the links."""
    return any(is_link_line(line) for line in lines) and all(
        is_link_line(line) or is_title(line) or all(i.italic for i in line.nonblank)
        for line in lines
    )


def find_front(doc: PdfDocument, layout: Layout) -> Front:
    """The front of the book, read by its links: the copyright page, the contents, the pieces,
    the reference sections and the reading plan."""
    front = Front()
    entries = sorted((e for e in doc.outline if e.page < layout.bible_start), key=lambda e: e.page)
    first = entries[0].page if entries else layout.bible_start
    page = copyright_page(doc, layout)
    if page is None or page >= first:
        front.errors.append("no copyright page before the first front section")
    else:
        end = first
        for number in range(page + 1, first):
            lines = _lines(doc, number, number + 1)
            if lines and _contents_page(lines):
                front.contents.append(number)
                end = min(end, number)
            elif lines and front.contents:
                front.errors.append(f"p{number}: a front page after the contents nothing explains")
        front.copyright = _lines(doc, page, end)
    for n, entry in enumerate(entries):
        end = entries[n + 1].page if n + 1 < len(entries) else layout.bible_start
        section = Section(entry.title, entry.page, end, _lines(doc, entry.page, end))
        body = section.body
        if body and all(is_link_line(line) for line in body):
            if front.plan is not None:
                front.errors.append(f"p{entry.page}: a second section of links only")
            front.plan = section
        elif sum(1 for line in body if carries_link(line)) * 2 > len(body):
            front.references.append(section)
        else:
            front.pieces.append(section)
    if front.plan is None:
        front.errors.append("no front section of links only (the reading plan)")
    return front


def title_lines(section: Section) -> tuple[list[Line], list[Line]]:
    """A section's printed title and anything else it sets at the title's size (a subtitle):
    the title is the run of title-size lines whose letters run into the outline name's end."""
    titles = [line for line in section.lines if is_title(line)]
    name = letters(section.title)
    taken: list[Line] = []
    for line in titles:
        joined = letters(" ".join(t.text for t in [*taken, line]))
        if joined and joined in name:
            taken.append(line)
        else:
            break
    return taken, titles[len(taken) :]


def title_agrees(section: Section, taken: Sequence[Line]) -> bool:
    printed = letters(" ".join(line.text for line in taken))
    return bool(printed) and letters(section.title).endswith(printed)


# --- writing -------------------------------------------------------------------------------


def italic_k(
    pieces: list[Piece], vocabulary: Vocabulary, fixes: Fixes, counts: Counter[str]
) -> list[Piece]:
    """The italic font's "k" break on a line that isn't justified (the notes' rule reads
    justified lines only): it joins when the rest is no word (S3a's rule), or when the head is
    no word and the rest a single letter or no common word ("Fork a", "Fork elsom", made up).
    A letter-spacing fix."""
    if not fixes.letter_spacing:
        return pieces

    def join(match: re.Match[str]) -> str:
        head, rest = match.group(1), match.group(2)
        lower = head.lower()
        if not vocabulary.is_word(rest) or (
            not vocabulary.is_word(lower) and (len(rest) == 1 or not vocabulary.is_common(rest))
        ):
            counts["italic k breaks"] += 1
            return head + rest
        return match.group(0)

    return [
        dataclasses.replace(p, text=_K_BREAK.sub(join, p.text)) if p.italic else p for p in pieces
    ]


Inline = Callable[[Sequence[Line]], list[Piece]]
Relink = Callable[[list[Piece]], tuple[list[Piece], list[str]]]


def _no_links(pieces: list[Piece]) -> tuple[list[Piece], list[str]]:
    return pieces, []


class Blocks:
    """One document's Markdown, block by block: each block's text rendered by the notes' rules
    and checked, what it prints kept for the consistency check."""

    def __init__(self, inline: Inline, relink_: Relink = _no_links) -> None:
        self.inline = inline
        self.relink = relink_
        self.markdown: list[str] = []
        self.plain: list[str] = []
        self.printed: list[str] = []
        self.problems: list[str] = []

    def text(
        self,
        lines: Sequence[Line] = (),
        *,
        pieces: list[Piece] | None = None,
        plain_style: bool = False,
        strip: str = "",
        targets: Sequence[str] | None = None,
    ) -> NoteText:
        """``lines``' (or ``pieces``') text. ``plain_style``: a head is set apart already, its
        weight stays out; ``strip``: a printed mark the Markdown carries otherwise (a list's
        bullet), dropped from the text's start; ``targets``: the ``ref:`` targets of
        ``pieces``' runs, already resolved (the reading plan)."""
        pieces = self.inline(lines) if pieces is None else pieces
        self.printed.append(" ".join(p.text for p in pieces))
        if strip and pieces and pieces[0].text.startswith(strip):
            rest = pieces[0].text[len(strip) :].lstrip()
            pieces = [dataclasses.replace(pieces[0], text=rest), *pieces[1:]]
            pieces = [p for p in pieces if p.text]
        if plain_style:
            pieces = [dataclasses.replace(p, bold=False, italic=False) for p in pieces]
        if targets is None:
            pieces, found = self.relink(pieces)
        else:
            found = list(targets)
        rendered = render(pieces, found, always=True)
        markdown = md(rendered)
        if not emphasis_ok(markdown):
            self.problems.append("emphasis-flanking")
        if plain_of(markdown) != rendered.plain:
            self.problems.append("markdown-round-trip")
        return rendered

    def add(self, markdown: str, plain: str) -> None:
        self.markdown.append(markdown)
        self.plain.append(plain)

    def head(self, lines: Sequence[Line]) -> None:
        t = self.text(lines, plain_style=True)
        self.add(f"## {md(t)}", t.plain)

    def paragraph(self, lines: Sequence[Line]) -> None:
        t = self.text(lines)
        self.add(md(t), t.plain)

    def broken(self, groups: Sequence[Sequence[Line]], *, first: str = "") -> None:
        """One paragraph whose printed lines (each a group: a line and its wrap) stay apart:
        hard breaks. ``first``: Markdown that opens it (a label)."""
        ts = [self.text(group) for group in groups]
        parts = [first] if first else []
        self.add("\\\n".join([*parts, *(md(t) for t in ts)]), "\n".join(t.plain for t in ts))

    def items(self, groups: Sequence[Sequence[Line]], *, strip: str = "") -> None:
        """A ``- `` list, one entry per group."""
        ts = [self.text(group, strip=strip) for group in groups]
        self.add("\n".join(f"- {md(t)}" for t in ts), "\n".join(t.plain for t in ts))

    @property
    def document(self) -> str:
        return "\n\n".join(self.markdown)

    @property
    def text_plain(self) -> str:
        return "\n\n".join(self.plain)

    def holds(self, printed: Sequence[Piece]) -> bool:
        """The blocks hold exactly the text the document prints, spaces aside."""
        return _WS_ALL.sub("", "".join(p.text for p in printed)) == _WS_ALL.sub(
            "", " ".join(self.printed)
        )


def md(text: NoteText) -> str:
    assert text.markdown is not None
    return text.markdown


def hygiene(
    found: dict[str, list[str]],
    name: str,
    plain: str,
    lines: list[Line],
    ctx: Context,
    problems: Iterable[str] = (),
) -> None:
    """The notes' hygiene and punctuation-spacing checks, the broken-word check and the
    Markdown checks, each failure filed under the document's name."""
    for problem in problems:
        found.setdefault(problem, []).append(name)
    checked = ADDRESS.sub("address", plain)
    for pattern_name, pattern in HYGIENE.items():
        if pattern.search(checked):
            found.setdefault(pattern_name, []).append(name)
    if broken_words(spaced(lines, ctx), ctx.vocabulary):
        found.setdefault("broken-word", []).append(name)


# --- the EPUB witness ----------------------------------------------------------------------


@dataclass(slots=True)
class Witnessed:
    """Each keyed part's text (fixed, raw, each fix alone), pages, and the words that find it
    in the EPUB, in the book's order."""

    texts: dict[Key, str] = field(default_factory=dict[Key, str])
    raw: dict[Key, str] = field(default_factory=dict[Key, str])
    solo: dict[str, dict[Key, str]] = field(default_factory=dict[str, dict[Key, str]])
    spans: dict[Key, tuple[int, int]] = field(default_factory=dict[Key, tuple[int, int]])
    openings: dict[Key, str] = field(default_factory=dict[Key, str])
    closings: dict[Key, str] = field(default_factory=dict[Key, str])
    order: list[Key] = field(default_factory=list[Key])

    def add(
        self,
        key: Key,
        lines: Sequence[Line],
        plain: Callable[[Fixes], str],
        *,
        opening: str | None = None,
    ) -> None:
        """``plain``: the part's text with the given fixes; ``opening``: the words that find
        it in the EPUB, when not its first few (a day's date)."""
        text = plain(Fixes())
        self.texts[key] = text
        none = Fixes.none()
        self.raw[key] = plain(none)
        for fix in dataclasses.fields(Fixes):
            self.solo.setdefault(fix.name, {})[key] = plain(
                dataclasses.replace(none, **{fix.name: True})
            )
        pages = [line.page for line in lines]
        self.spans[key] = (min(pages), max(pages))
        words = text.split()
        self.openings[key] = opening if opening is not None else " ".join(words[:OPEN_WORDS])
        self.closings[key] = " ".join(words[-OPEN_WORDS:])
        self.order.append(key)

    def extend(self, other: Witnessed) -> None:
        self.texts.update(other.texts)
        self.raw.update(other.raw)
        for name, texts in other.solo.items():
            self.solo.setdefault(name, {}).update(texts)
        self.spans.update(other.spans)
        self.openings.update(other.openings)
        self.closings.update(other.closings)
        self.order += other.order


@dataclass(slots=True)
class EpubDocuments:
    texts: dict[Key, str] = field(default_factory=dict[Key, str])
    damaged: set[Key] = field(default_factory=set[Key])
    lost: list[Key] = field(default_factory=list[Key])  # parts whose opening the EPUB lacks


def _pattern(words: str, *, opening: bool, loose: bool = False) -> re.Pattern[str]:
    """Words as the EPUB may space them; an opening can't run on into a digit ("…day 1" is not
    "…day 10"). ``loose``: the EPUB's damage may have run the words into each other or glued a
    scrap before them."""
    gaps = "[\\s\xa0]*" if loose else "[\\s\xa0]+"
    # the EPUB's markup can set a mark apart from its word ("word ,", "2: 5"): inside a word
    # a space is optional between letters and marks
    body = gaps.join(
        "[\\s\xa0]*".join(re.escape(p) for p in _TOKENS.findall(w)) for w in words.split()
    )
    return re.compile(("" if loose else "(?<!\\w)") + body + (r"(?!\d)" if opening else ""))


def epub_cut(flat: str, witnessed: Witnessed) -> EpubDocuments:
    """Each part's EPUB text: from its opening words to the next part's, ended at its own
    closing words (the last time they stand there). The words are found in the text with the
    dropped-text marks taken out (the EPUB leaves one inside a link's words, "Name␀,"); a part
    found only loosely, or holding a mark, is damaged."""
    out = EpubDocuments()
    breaks = [m.start() for m in re.finditer(BREAK, flat)]
    shift = [b - n for n, b in enumerate(breaks)]  # where each mark sat in the text without them
    clean = flat.replace(BREAK, "")

    def at_start(c: int) -> int:
        return c + bisect.bisect_right(shift, c)

    def at_end(c: int) -> int:
        return c + bisect.bisect_left(shift, c)

    starts: list[tuple[Key, int | None]] = []
    at = 0
    for key in witnessed.order:
        opening = witnessed.openings[key]
        found = _pattern(opening, opening=True).search(clean, at)
        if found is None:
            found = _pattern(opening, opening=True, loose=True).search(clean, at)
            if found is not None:
                out.damaged.add(key)
        starts.append((key, found.start() if found is not None else None))
        if found is not None:
            at = found.end()
    found_at = [s for _, s in starts if s is not None]
    previous: Key | None = None
    for key, start in starts:
        if start is None:
            out.lost.append(key)
            out.texts[key] = ""
            if previous is not None:
                out.damaged.add(previous)  # its text ran on into this part's
            continue
        later = [s for s in found_at if s > start]
        end = later[0] if later else len(clean)
        closing = list(_pattern(witnessed.closings[key], opening=False).finditer(clean, start, end))
        if closing:
            end = closing[-1].end()
        else:
            out.damaged.add(key)
            end = min(end, start + 2 * len(witnessed.texts[key]) + 200)
        part = flat[at_start(start) : at_end(end)]
        if BREAK in part:
            out.damaged.add(key)
            part = part.replace(BREAK, " ")
        out.texts[key] = _WS.sub(" ", part).strip()
        previous = key
    return out


def cross_check(
    witnessed: Witnessed,
    epub: EpubDocuments,
    doc: PdfDocument,
    verse_texts: dict[Key, str],
) -> CrossCheck:
    """The documents' text, PDF vs EPUB, with the notes' classes and evidence rules."""
    wanted = {page for first, last in witnessed.spans.values() for page in range(first, last + 1)}
    pages: dict[int, list[str]] = {}
    for item in doc.items:
        if item.page in wanted:
            pages.setdefault(item.page, []).append(item.text)
    return cross_check_notes(
        fixed=witnessed.texts,
        raw=witnessed.raw,
        solo=witnessed.solo,
        epub=epub.texts,
        epub_damaged=epub.damaged,
        context_texts={**verse_texts, **witnessed.texts},
        pages={page: " ".join(t) for page, t in pages.items()},
        spans=witnessed.spans,
    )
