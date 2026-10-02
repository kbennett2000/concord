"""The study notes: anchors, passages and the references they link (V8-S2b).

The last region of the book holds the study notes, book by book after a 66-entry index. Each
note opens with a heading line — a bold book abbreviation and a blue bold reference ("Gen. "
"1:26-27") — and runs, one paragraph, to the next heading. The reference gives the note's
passages: ``C:V``, ``C:V-V``, ``C:V–C:V``, and lists of those joined by ``,`` (same chapter)
or ``;`` (a new ``C:``).

**Anchor.** The book calls each note out with a blue verse number in the Bible text
(``text.Callout``). A note anchors at the start of the verse that calls it out, or, when it has
no callout of its own (it shares a first verse with another note), at the start of its first
verse.

**Links.** Blue references in a note's text link into the Bible. Each becomes a ``ref:`` link
(ADR-0011). The text decides the book: a book the link names; else, for a bare reference
continuing a ``;``/``,`` list, the book before it; else the note's own book. The link's own
target page is evidence only — the book resolved some bare references to the last book
named, and pointed a few named ones elsewhere — so each disagreement is classified.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from bible_core.normalize import normalize

from emb_convert.layout import Layout
from emb_convert.lines import Line, group_lines
from emb_convert.notetext import Piece
from emb_convert.pdfxml import PdfDocument, TextItem
from emb_convert.skeleton import NLT_EXTRA
from emb_convert.text import Callout

SINGLE_CHAPTER = frozenset({"OBA", "PHM", "2JN", "3JN", "JUD"})

_HEAD = re.compile(r"^((?:[1-3] )?[A-Z][a-z]+(?: of [A-Z][a-z]+)?)\.? (\d.*)$")
_PART = re.compile(r"(\d+)(?::(\d+))?(?:-(?:(\d+):)?(\d+))?")
_DASHES = re.compile(r"\s*[-–—]\s*")

Key = tuple[str, int, int]


@dataclass(frozen=True, slots=True)
class Part:
    start_chapter: int
    start_verse: int
    end_chapter: int
    end_verse: int


@dataclass(slots=True)
class StudyNote:
    book: str
    heading: str  # as printed: "Gen. 1:26-27" (a reference, no text)
    reference: str  # the reference alone, spaces dropped and dashes as "-": "1:26-27"
    parts: list[Part]
    page: int
    lines: list[Line]  # the body

    @property
    def first(self) -> tuple[int, int]:
        return self.parts[0].start_chapter, self.parts[0].start_verse


@dataclass(slots=True)
class StudyRegion:
    notes: list[StudyNote] = field(default_factory=list[StudyNote])
    errors: list[str] = field(default_factory=list[str])


def parse_parts(book: str, reference: str) -> list[Part] | str:
    """``1:9-11, 14-15`` / ``1:22-2:8`` / ``13:23; 19:26`` → parts, or an error message."""
    parts: list[Part] = []
    chapter: int | None = 1 if book in SINGLE_CHAPTER else None
    for group in reference.split(";"):
        for piece in group.split(","):
            match = _PART.fullmatch(piece)
            if match is None:
                return f"{book} {reference}: part {piece!r}"
            c1, v1, c2, v2 = match.groups()
            if v1 is None:  # no colon: a verse in the chapter so far
                if chapter is None:
                    return f"{book} {reference}: {piece!r} has no chapter"
                start = (chapter, int(c1))
                end = (int(c2) if c2 else chapter, int(v2)) if v2 else start
            else:
                start = (int(c1), int(v1))
                end = (int(c2) if c2 else start[0], int(v2)) if v2 else start
            if end < start:
                return f"{book} {reference}: {piece!r} ends before it starts"
            chapter = end[0]
            parts.append(Part(*start, *end))
    return parts


def parse_study(doc: PdfDocument, layout: Layout, by_alias: dict[str, str]) -> StudyRegion:
    """Every study note, in book order: its book, reference parts and body lines."""
    region = StudyRegion()
    lines = group_lines([i for i in doc.items if i.page >= layout.study_start])
    heads = [
        n
        for n, line in enumerate(lines)
        if line.nonblank
        and line.nonblank[0].bold
        and not line.nonblank[0].blue
        and any(i.blue and i.bold for i in line.nonblank)
    ]
    for n, at in enumerate(heads):
        line = lines[at]
        heading = " ".join(line.text.split())
        match = _HEAD.match(heading)
        book = by_alias.get(normalize(match.group(1))) if match else None
        if match is None or book is None:
            region.errors.append(f"study-note heading {heading!r} on p{line.page}")
            continue
        reference = _DASHES.sub("-", match.group(2)).replace(" ", "")
        parts = parse_parts(book, reference)
        if isinstance(parts, str):
            region.errors.append(f"{parts} on p{line.page}")
            continue
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        region.notes.append(
            StudyNote(book, heading, reference, parts, line.page, lines[at + 1 : end])
        )
    return region


def shape(note: StudyNote, last_verse: dict[tuple[str, int], int]) -> str:
    """verse · range · whole chapter · cross-chapter · multi-part (they don't overlap)."""
    if len(note.parts) > 1:
        return "multi-part"
    part = note.parts[0]
    if part.start_chapter != part.end_chapter:
        return "cross-chapter"
    if part.start_verse == part.end_verse:
        return "verse"
    whole = last_verse.get((note.book, part.start_chapter))
    if part.start_verse == 1 and part.end_verse == whole:
        return "whole chapter"
    return "range"


def covers(note: StudyNote, chapter: int, verse: int) -> bool:
    return any(
        (p.start_chapter, p.start_verse) <= (chapter, verse) <= (p.end_chapter, p.end_verse)
        for p in note.parts
    )


@dataclass(slots=True)
class Callouts:
    at: dict[int, tuple[int, int]] = field(default_factory=dict[int, tuple[int, int]])
    unmatched: list[Callout] = field(default_factory=list[Callout])


def assign_callouts(notes: list[StudyNote], callouts: list[Callout]) -> Callouts:
    """Give each callout to the note it calls out: on its target page (±1), in its book, its
    passages covering the callout's verse — one starting there first, then book order."""
    result = Callouts()
    by_page: dict[int, list[int]] = {}
    for n, note in enumerate(notes):
        by_page.setdefault(note.page, []).append(n)
    for callout in callouts:
        candidates = [
            n
            for page in (callout.target_page - 1, callout.target_page, callout.target_page + 1)
            for n in by_page.get(page, [])
            if n not in result.at
            and notes[n].book == callout.book
            and covers(notes[n], callout.chapter, callout.verse)
        ]
        starting = [n for n in candidates if notes[n].first == (callout.chapter, callout.verse)]
        chosen = sorted(starting or candidates)
        if not chosen:
            result.unmatched.append(callout)
            continue
        result.at[chosen[0]] = (callout.chapter, callout.verse)
    return result


def passages(note: StudyNote, anchor: tuple[int, int]) -> list[Part]:
    """The note's parts, or none when it is the single verse it anchors at."""
    part = note.parts[0]
    single = (part.start_chapter, part.start_verse) == (part.end_chapter, part.end_verse)
    if len(note.parts) == 1 and single and anchor == note.first:
        return []
    return list(note.parts)


# --- links ---------------------------------------------------------------------------------


@dataclass(slots=True)
class LinkRun:
    page: int | None  # the PDF page the book links it to
    items: list[TextItem] = field(default_factory=list[TextItem])


def link_runs(
    lines: list[Line], is_link: Callable[[TextItem], bool] | None = None
) -> tuple[dict[int, int], list[LinkRun]]:
    """Consecutive blue items form one link (it may wrap over lines or split into items); a
    blue item with no target continues the link before it. ``is_link``: which blue items are
    links into the Bible (articles: not a footnote's marker)."""
    run_of: dict[int, int] = {}
    runs: list[LinkRun] = []
    current: LinkRun | None = None
    for line in lines:
        for item in line.items:
            if item.blue and (is_link is None or is_link(item)):
                if current is None or (
                    item.link_page is not None and item.link_page != current.page
                ):
                    current = LinkRun(item.link_page)
                    runs.append(current)
                current.items.append(item)
                run_of[id(item)] = len(runs) - 1
            elif item.stripped:
                current = None
    return run_of, runs


@dataclass(frozen=True, slots=True)
class RefPart:
    start: int  # slice of the link's text this reference spans
    end: int
    target: str  # ADR-0011: "GEN.1.26", "PSA.51", "GEN.1-2", "EXO.7.1-12.51"
    book: str
    chapter: int
    verse: int  # the first verse (1 for a chapter)


@dataclass(frozen=True, slots=True)
class RunRefs:
    parts: list[RefPart]
    book: str
    chapter: int | None  # the chapter a following ", N" continues
    named: bool


_NAMED = re.compile(r"((?:[1-3] )?[A-Z][a-z]+(?: of [A-Z][a-z]+)?) (?=\d)")
_CHAPTER_WORD = re.compile(r"^(?:chapters?|chs?\.) ", re.IGNORECASE)  # "Chapters 1–3" (S5b)
_VERSE_WORD = re.compile(r"^vv?\. ")  # "v. 25", "vv. 3-5": verses of the note's chapter
_REF = re.compile(r"(\d+)(?::(\d+))?(?:\s*[-–]\s*(\d+)(?::(\d+))?)?(?:ff)?")
_SEPARATOR = re.compile(r"\s*([,;])\s*")


def _target(book: str, c1: int, v1: int | None, c2: int | None, v2: int | None) -> str:
    if v1 is None:
        return f"{book}.{c1}" if c2 is None or c2 == c1 else f"{book}.{c1}-{c2}"
    if v2 is None or (c2 in (None, c1) and v2 == v1):
        return f"{book}.{c1}.{v1}"
    if c2 is None or c2 == c1:
        return f"{book}.{c1}.{v1}-{v2}"
    return f"{book}.{c1}.{v1}-{c2}.{v2}"


def resolve_run(
    text: str,
    *,
    note_book: str,
    continues: tuple[str, int | None, str] | None,
    page_book: str | None,
    by_alias: dict[str, str],
    names: dict[str, str],
    note_chapter: int | None = None,
) -> RunRefs | str:
    """A link's text → its references, or an error message.

    ``continues``: (book, chapter, separator) when only ``;``/``,`` stands between this link
    and the one before. ``page_book``: the book of the link's target page, used only to
    complete a name cut by the link's edge ("1 " + "Corinthians 6:19"). ``note_chapter``:
    the chapter "v. 25" means (an article on one chapter); without it such a link is an
    error. A later book named after a ``,``/``;`` inside the link starts its own reference,
    and a verse's "ff" ("and following") keeps the verse.
    """
    named = _NAMED.match(text)
    word = _CHAPTER_WORD.match(text)  # "chapter 9", "chapters 17–21": the note's own book
    verses = _VERSE_WORD.match(text)
    at = 0
    chapter: int | None = None
    if verses is not None:
        if note_chapter is None:
            return f"link {text!r}: a verse of no known chapter"
        book, at, chapter = note_book, verses.end(), note_chapter
    elif word is not None:
        book, at = note_book, word.end()
    elif named is not None:
        name = named.group(1)
        book = by_alias.get(normalize(name)) or ""
        if not book and page_book is not None and names[page_book].endswith(name):
            book = page_book
        if not book:
            return f"link {text!r}: unknown book {name!r}"
        at = named.end()
    elif continues is not None:
        book = continues[0]
        chapter = continues[1] if continues[2] == "," else None
    else:
        book = note_book
    parts: list[RefPart] = []
    separator = "," if verses is not None else ""
    while at < len(text):
        later = _NAMED.match(text, at) if parts else None
        named_at: int | None = None
        if later is not None and (found := by_alias.get(normalize(later.group(1)))):
            book, named_at, at, chapter, separator = found, later.start(), later.end(), None, ""
        match = _REF.match(text, at)
        if match is None:
            return f"link {text!r}: cannot read {text[at:]!r}"
        a, b, c, d = (int(g) if g else None for g in match.groups())
        assert a is not None
        if b is not None:  # C:V…
            c1, v1 = a, b
            c2, v2 = (c, d) if d is not None else (a, c)
        elif book in SINGLE_CHAPTER and word is None:
            c1, v1, c2, v2 = 1, a, 1, c
        elif separator == "," and chapter is not None:  # ", 46" — a verse in that chapter
            c1, v1, c2, v2 = chapter, a, chapter, c
        else:  # a chapter or chapter range
            c1, v1, c2, v2 = a, None, c, None
        if (c2 or c1, v2 or v1 or 0) < (c1, v1 or 0):
            return f"link {text!r}: {match.group(0)!r} ends before it starts"
        # the first reference's link text keeps the book or "chapter" printed before it
        begin = 0 if not parts else named_at if named_at is not None else match.start()
        parts.append(RefPart(begin, match.end(), _target(book, c1, v1, c2, v2), book, c1, v1 or 1))
        chapter = (c2 or c1) if v1 is not None else None
        at = match.end()
        sep = _SEPARATOR.match(text, at)
        if at < len(text) and sep is None:
            return f"link {text!r}: cannot read {text[at:]!r}"
        if sep is not None:
            separator = sep.group(1)
            at = sep.end()
    if not parts:
        return f"link {text!r}: no reference"
    return RunRefs(parts, book, chapter, named is not None)


def separators(pieces: list[Piece]) -> dict[int, str]:
    """For each link run, the text between it and the link before it ("" for the first)."""
    out: dict[int, str] = {}
    between: str | None = None
    for piece in pieces:
        if piece.run is None:
            if between is not None:
                between += piece.text
            continue
        if piece.run not in out:
            out[piece.run] = between if between is not None else ""
        between = ""
    return out


def exists(skeleton: dict[tuple[str, int], int], book: str, chapter: int, verse: int) -> bool:
    count = skeleton.get((book, chapter))
    return count is not None and (verse <= count or (book, chapter, verse) in NLT_EXTRA)


def target_verses(target: str) -> list[tuple[str, int, int]]:
    """The first and last verse a ``ref:`` target names (verse 1 for a chapter)."""
    book, _, rest = target.partition(".")
    if "." not in rest:
        first, _, last = rest.partition("-")
        return [(book, int(first), 1), (book, int(last or first), 1)]
    chapter, _, verses = rest.partition(".")
    v1, _, end = verses.partition("-")
    if "." in end:
        c2, _, v2 = end.partition(".")
        return [(book, int(chapter), int(v1)), (book, int(c2), int(v2))]
    return [(book, int(chapter), int(v1)), (book, int(chapter), int(end or v1))]
