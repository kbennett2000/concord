"""The EPUB's textual and study notes — a witness for the PDF's note text, never a source.

The EPUB flattens the notes into runs of styled text (V8-S2b, measured):

- a textual-notes block opens with a plain run "<Book> <N> Textual Notes" (a few are
  ``<h1>``); each note opens with a bold label ("3:8", "60:" + small-caps "TITLE"). The block
  run ends at the feature index that follows ("MEN, WOMEN, AND GOD INDEX");
- the study notes follow the feature region; each opens with a bold heading ("Gen. 1:1").
  The region starts at the PDF's first study-note heading.

Conversion damage shows as scraps, including inside labels and headings
("filepos=0000562640 >3:16", "Gen. 00542616 >1:2"); such a label is read past its last ">" and
its note flagged damaged. A dropped-text break (an empty, attribute-less ``<a>``, or a double
space inside a run) becomes ``epub.BREAK``, as in the verse witness.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from bible_core.normalize import normalize

from emb_convert.epub import BREAK, spine_documents

Key = tuple[str, int, int]

# (a numbered book's name can carry a no-break space: "1\u00a0Thessalonians")
_HEADER = re.compile(
    r"((?:(?<![\w-])[1-3][ \xa0]+)?[A-Z][a-z]+(?:[ \xa0]+of[ \xa0]+[A-Z][a-z]+)?)"
    r"[ \xa0]+(\d+)[ \xa0]+Textual[ \xa0]+Notes"
)
SINGLE_CHAPTER = frozenset({"OBA", "PHM", "2JN", "3JN", "JUD"})
_INDEX = re.compile(r"\b[A-Z][A-Z,’' ]+ INDEX\b")
_LABEL = re.compile(r"^(?:\d+:)?\d+[a-e]?(?:-(?:\d+:)?\d+[a-e]?)?$|^\d+:TITLE$")
_HEAD = re.compile(r"^((?:[1-3] )?[A-Z][a-z]+(?: of [A-Z][a-z]+)?)\.?\s*(.*)$")
_REFERENCE = re.compile(r"^\d+(?::\d+)?(?:[-,;:]\d+)*")
_DASHES = re.compile(r"\s*[-–—]\s*")
_GAP = re.compile(r"(?<=\S) {2,}(?=\S)")
_WS = re.compile(r"\s+")


@dataclass(slots=True)
class EpubNotes:
    textual: dict[tuple[str, int, str, int], str] = field(
        default_factory=dict[tuple[str, int, str, int], str]
    )
    study: dict[tuple[str, str, int], str] = field(default_factory=dict[tuple[str, str, int], str])
    damaged: set[tuple[str, ...]] = field(default_factory=set[tuple[str, ...]])


@dataclass(slots=True)
class _Run:
    text: str
    bold: bool


class _Tokens(HTMLParser):
    """Text runs with their boldness (italics flattened); blocks and ``<br>`` become spaces."""

    BLOCKS = frozenset({"p", "div", "h1", "h2", "h3", "li", "br", "tr", "td"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.runs: list[_Run] = []
        self.stack: list[str] = []
        self.bare_anchor = False

    def emit(self, text: str, bold: bool) -> None:
        if self.runs and self.runs[-1].bold == bold:
            self.runs[-1].text += text
        else:
            self.runs.append(_Run(text, bold))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCKS:
            self.emit(" ", False)
        if tag in ("img", "br", "hr", "meta", "link"):
            return
        if tag == "a":
            self.bare_anchor = not attrs
        self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.bare_anchor:
            self.bare_anchor = False
            self.emit(BREAK, False)
        if tag in self.BLOCKS:
            self.emit(" ", False)
        if tag in self.stack:
            while self.stack:
                if self.stack.pop() == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self.bare_anchor and data.strip():
            self.bare_anchor = False
        if "sup" in self.stack:
            data = f" {data} "  # a small verse number inside a quoted reading
        bold = "b" in self.stack or "strong" in self.stack
        self.emit(data if bold else _GAP.sub(f" {BREAK} ", data), bold)


def _clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _past_scraps(text: str) -> tuple[str, bool]:
    """A label or heading read past its conversion scraps ("filepos=… >3:16" → "3:16")."""
    if ">" in text:
        return text.rsplit(">", 1)[1], True
    return text, False


def parse_epub_notes(
    path: Path,
    by_alias: dict[str, str],
    first_study: tuple[str, str],
    books: list[str],
) -> EpubNotes:
    """Read ``path``'s notes. ``first_study``: the PDF's first study note (book, reference),
    where the EPUB's study region starts. ``books``: the books with textual notes, in order —
    the EPUB dropped a few block headers ("Exodus 1 Textual Notes"), and a label whose
    chapter goes back (or a "C:V" label after a single-chapter book's bare ones) means the
    next of these books."""
    tokens = _Tokens()
    with zipfile.ZipFile(path) as archive:
        for name in spine_documents(archive):
            if name.endswith((".html", ".xhtml", ".htm")):
                tokens.feed(archive.read(name).decode("utf-8", errors="replace"))
                tokens.emit(" ", False)
    tokens.close()
    return _scan(tokens.runs, by_alias, first_study, books)


def _scan(
    runs: list[_Run], by_alias: dict[str, str], first_study: tuple[str, str], books: list[str]
) -> EpubNotes:
    notes = EpubNotes()
    mode = "before"
    block: tuple[str, int] | None = None
    last_chapter = 0
    seen: dict[tuple[str, ...], int] = {}
    key: tuple[str, ...] | None = None
    parts: list[str] = []

    def flush() -> None:
        nonlocal key, parts
        if key is not None:
            text = _clean("".join(parts))
            if len(key) == 4:
                notes.textual[(key[0], int(key[1]), key[2], int(key[3]))] = text
            else:
                notes.study[(key[0], key[1], int(key[2]))] = text
        key, parts = None, []

    def occurrence(base: tuple[str, ...]) -> str:
        seen[base] = seen.get(base, 0) + 1
        return str(seen[base])

    for run in runs:
        if not run.bold:
            text = run.text
            at = 0
            while mode in ("before", "textual"):
                # a run of plain text can hold a note's end, then the next block's header
                header = _HEADER.search(text.replace(BREAK, " "), at)
                if header is None:
                    break
                code = by_alias.get(normalize(" ".join(header.group(1).split())))
                if code is None:
                    at = header.end()
                    continue
                if key is not None:
                    parts.append(text[: header.start()])
                flush()
                block, mode = (code, int(header.group(2))), "textual"
                last_chapter = block[1]
                text, at = text[header.end() :], 0
            if mode == "textual":
                end = _INDEX.search(text)
                if end is not None:  # the feature index that follows the last block
                    if key is not None:
                        parts.append(text[: end.start()])
                    flush()
                    mode = "features"
                    continue
            if key is not None:
                parts.append(text)
            continue
        text = _clean(run.text.replace(BREAK, " "))
        bold, damaged = _past_scraps(text)
        if mode == "textual" and block is not None:
            label = bold.replace(" ", "")
            bare_ok = ":" in label or block[0] in SINGLE_CHAPTER or label == str(block[1])
            if _LABEL.match(label) and bare_ok:
                flush()
                # a "C:V" label names its own chapter (a damaged or lost header can't)
                chapter = int(label.split(":", 1)[0]) if ":" in label else block[1]
                lost = ":" in label and (chapter < last_chapter or block[0] in SINGLE_CHAPTER)
                if lost and block[0] in books and books.index(block[0]) + 1 < len(books):
                    block = (books[books.index(block[0]) + 1], chapter)
                last_chapter = chapter
                base = (block[0], str(chapter), label)
                key = (*base, occurrence(base))
                if damaged:
                    notes.damaged.add(key)
                continue
        if mode in ("features", "study", "textual"):
            head = _HEAD.match(text)  # the abbreviation first, then the reference past any scrap
            code = by_alias.get(normalize(head.group(1))) if head else None
            printed, damaged = _past_scraps(head.group(2)) if head else ("", False)
            reference = _DASHES.sub("-", printed).replace(" ", "")
            found = _REFERENCE.match(reference)
            if found is not None and found.end() < len(reference):
                reference, damaged = found.group(0), True  # a scrap after the reference
            if head and code and found is not None:
                if mode != "study" and (code, reference) == first_study:
                    flush()
                    mode = "study"
                if mode == "study":
                    flush()
                    base = (code, reference)
                    key = (*base, occurrence(base))
                    if damaged:
                        notes.damaged.add(key)
                    continue
        if key is not None:
            parts.append(run.text)
    flush()
    return notes
