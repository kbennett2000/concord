"""Parse the EPUB edition into verses and headings — a witness, never a source.

The EPUB is a separate Calibre conversion of the same Kindle book. Its conversion dropped and
fused words and left markup scraps, so it is only used to cross-check the PDF parse
(``crosscheck.py``). Its structure:

- chapter header: a block of ``<big>`` text, the book name then the chapter number;
- verse number: ``<sup>`` text (``"12"``, ``"20-21"``, ``"11:1"``);
- heading: a block whose text is all bold *and* italic;
- callout: bold (not italic) text, usually with a banner image — never verse text;
- Perspectives box: the content between a pair of ``<hr>`` rules — never verse text (its text
  is kept for the boxes' witness, V8-S3b);
- italic-only blocks follow the same rules as the PDF parse (psalm titles prefixed to verse
  1; Ps 119 stanza and Song of Songs speaker labels as headings; otherwise verse text);
- a dropped-text break (``BREAK`` in the verse text): an empty ``<a>`` with no attributes,
  or a double space inside a text run where a word was removed ("his  message").
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from bible_core.normalize import normalize
from bible_core.seed import BookSeed

PSALMS = "PSA"
SONG = "SNG"
STANZA_PSALM = 119
SINGLE_CHAPTER = frozenset({"OBA", "PHM", "2JN", "3JN", "JUD"})

_VERSE = re.compile(r"(?:(\d+):)?(\d+)(?:-(\d+))?")
_WORDS = re.compile(r"[A-Za-z]{2,}[ ,;]+[A-Za-z]{2,}")  # real words, not a "small>" scrap
_GAP = re.compile(r"(?<=\S) {2,}(?=\S)")  # a word-sized hole the conversion left mid-text
_NAME_SCRAP = re.compile(r"[^A-Za-z0-9 ]")
MAX_VERSE = 176  # Psalm 119; a larger "verse number" is a conversion scrap
_WS = re.compile(r"\s+")

Key = tuple[str, int, int]

# Where the conversion dropped text it left an empty, attribute-less <a>. The parser keeps a
# sentinel there so the cross-check can tell "the EPUB shows a break at this spot".
BREAK = "\ue000"


class EpubError(Exception):
    """The EPUB can't be read as expected."""


@dataclass(slots=True)
class EpubBible:
    verses: dict[Key, str] = field(default_factory=dict[Key, str])
    headings: dict[tuple[str, int], list[str]] = field(
        default_factory=dict[tuple[str, int], list[str]]
    )
    damaged: set[Key] = field(default_factory=set[Key])  # scraps seen by the parser itself
    boxes: list[str] = field(default_factory=list[str])  # each Perspectives box's text (V8-S3b)


def spine_documents(archive: zipfile.ZipFile) -> list[str]:
    """The EPUB's content documents in reading order."""
    container = ET.fromstring(archive.read("META-INF/container.xml"))
    rootfile = next(
        (el.get("full-path") for el in container.iter() if el.tag.endswith("rootfile")), None
    )
    if not rootfile:
        raise EpubError("META-INF/container.xml names no rootfile")
    opf = ET.fromstring(archive.read(rootfile))
    base = posixpath.dirname(rootfile)
    manifest = {
        el.get("id", ""): el.get("href", "") for el in opf.iter() if el.tag.endswith("item")
    }
    return [
        posixpath.normpath(posixpath.join(base, manifest[el.get("idref", "")]))
        for el in opf.iter()
        if el.tag.endswith("itemref") and el.get("idref", "") in manifest
    ]


@dataclass(slots=True)
class _Block:
    text: list[tuple[str, bool, bool]] = field(default_factory=list[tuple[str, bool, bool]])
    big: list[str] = field(default_factory=list[str])

    def plain(self) -> str:
        return "".join(t for t, _, _ in self.text)


class _Reader(HTMLParser):
    """Streams the spine's documents and builds verses and headings."""

    BLOCKS = frozenset({"p", "div", "h1", "h2", "h3", "h4", "li", "br"})

    def __init__(self, seeds: list[BookSeed], skeleton: dict[tuple[str, int], int]) -> None:
        super().__init__(convert_charrefs=True)
        self.skeleton = skeleton
        self.by_alias = {alias: seed.id for seed in seeds for alias in seed.aliases}
        self.out = EpubBible()
        self.stack: list[str] = []
        self.bold_skip_depth: int | None = None
        self.in_box = False
        self.boxes = 0
        self.box_text: list[str] = []
        self.bare_anchor = False
        self.block = _Block()
        self.book: str | None = None
        self.chapter = 0
        self.verse: tuple[int, int] | None = None
        self.parts: list[str] = []
        self.title: list[str] = []
        self.pending_headings: list[str] = []

    # -- tag tracking

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "hr":
            self.end_block()
            if self.chapter:  # intros use rules too; only chapters hold boxes
                self.close_box()
                self.in_box = not self.in_box
                self.boxes += self.in_box
            return
        if tag in self.BLOCKS:
            self.end_block()
            if self.in_box:
                self.box_text.append(" ")
        if tag in ("img", "br", "hr", "meta", "link"):
            return
        if tag == "a":
            self.bare_anchor = not attrs
        elif tag == "sup":
            self.bare_anchor = False  # <a><sup>N</sup></a> wraps a verse number
        self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.bare_anchor:
            self.bare_anchor = False
            self.block.text.append((BREAK, False, False))
        if tag in self.BLOCKS:
            self.end_block()
        if tag in self.stack:
            while self.stack:
                if self.stack.pop() == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self.in_box:
            self.box_text.append(data)
            return
        if not data:
            return
        if self.bare_anchor and data.strip():
            self.bare_anchor = False
            if not data.strip().startswith("*"):  # <a>*</a> is a dead note link, not a break
                self.block.text.append((BREAK, False, False))
        if "sup" in self.stack:
            if _WORDS.search(data) and not _VERSE.search(data):
                # words trapped in an unclosed <sup>, shown as superscript: visible damage
                # (usually text spliced from elsewhere, so it is not kept)
                self.damage()
                return
            self.end_block()
            self.verse_number(data.strip())
            return
        if "big" in self.stack:
            if data.strip():
                self.block.big.append(data.strip())
            return
        bold = "b" in self.stack or "strong" in self.stack
        italic = "i" in self.stack or "em" in self.stack
        self.block.text.append((_GAP.sub(f" {BREAK} ", data), bold, italic))

    def close_box(self) -> None:
        """A box ends (its closing rule, or a chapter header): keep its text."""
        if self.in_box:
            self.out.boxes.append(_WS.sub(" ", "".join(self.box_text)).strip())
        self.box_text = []

    # -- blocks

    def end_block(self) -> None:
        block, self.block = self.block, _Block()
        if block.big:
            self.big_block(block.big)
        words = [(t, b, i) for t, b, i in block.text if t.strip()]
        if not words:
            if block.text and self.verse is not None:
                self.parts.append(" ")
            return
        if self.book is None or self.chapter == 0:
            return  # intro or front matter
        text = block.plain()
        if self.book == PSALMS and self.chapter != STANZA_PSALM and self.verse is None:
            title = "".join(t for t, b, i in block.text if i and not b)
            if title.strip():  # a psalm title can share its block with header scraps
                self.title.append(title)
            return
        if all(b and i for _, b, i in words):
            self.heading(text)
        elif all(i and not b for _, b, i in words):
            self.italic(text)
        else:
            for t, b, i in block.text:
                if b and not i:
                    continue  # a callout label (and any banner-image scrap inside it)
                self.add(t)
            self.parts.append(" ")

    def big_block(self, big: list[str]) -> None:
        tokens = [_NAME_SCRAP.sub("", t).strip() for t in big]
        names = [self.by_alias.get(normalize(t)) for t in tokens if t and not t.isdigit()]
        code = next((c for c in names if c is not None), None)
        number = next((t for t in tokens if t.isdigit()), None)
        if code is None:
            return
        self.close_box()
        self.in_box = False
        if code != self.book:
            self.flush()
            self.book, self.chapter = code, 0
            self.pending_headings = []
        if number is not None:
            n = int(number)
            if n != self.chapter:
                self.flush()
                self.chapter = n
                self.title = []

    def heading(self, text: str) -> None:
        self.pending_headings.append(_clean(text.replace(BREAK, "")))

    def italic(self, text: str) -> None:
        assert self.book is not None
        if (self.book == PSALMS and self.chapter == STANZA_PSALM) or self.book == SONG:
            self.heading(text)
        elif self.book == PSALMS and self.verse is None:
            self.title.append(text)
        else:
            self.add(text)
            self.parts.append(" ")

    def add(self, text: str) -> None:
        if self.verse is None:
            return
        if self.pending_headings:
            self.attach_headings()
        self.parts.append(text)

    def attach_headings(self) -> None:
        assert self.book is not None
        self.out.headings.setdefault((self.book, self.chapter), []).extend(self.pending_headings)
        self.pending_headings = []

    # -- verses

    def verse_number(self, text: str) -> None:
        """Take a ``<sup>`` verse number, repairing the conversion's damage where it can.

        Numbers arrive with scraps ("28mall>"), fused text ("37 accordhe") or a dropped digit
        ("2" where 22 belongs). The next expected number is accepted; a near miss becomes the
        expected number and the verse is flagged damaged; a stray "1" only starts a new
        chapter when the current one is complete by the KJV skeleton (its header was lost).
        """
        match = _VERSE.search(text)
        if match is None or self.book is None:
            return
        scrap = text.strip() != match.group(0)
        label, first = match.group(1), int(match.group(2))
        last = int(match.group(3) or first)
        if label is not None and int(label) != self.chapter:
            self.flush()
            self.chapter = int(label)
            self.title = []
        if self.chapter == 0:
            if self.book in SINGLE_CHAPTER and first == 1:
                self.chapter = 1
            else:
                return
        current = self.verse[1] if self.verse is not None else 0
        expected = current + 1
        if first == 1 and current > 1:
            if current < self.skeleton.get((self.book, self.chapter), 0) - 1:
                self.damage()
                return
            self.flush()
            self.chapter += 1  # the chapter header was lost in conversion
            self.title = []
        elif not expected <= first <= current + 3:
            near = str(first)
            if first > MAX_VERSE or str(expected).startswith(near) or str(expected).endswith(near):
                first = last = expected
                scrap = True
            else:
                self.damage()
                return
        self.flush()
        self.verse = (first, last)
        if scrap:
            self.out.damaged.add((self.book, self.chapter, first))
        if self.pending_headings:
            self.attach_headings()
        if first == 1 and self.title:
            self.parts = [" ".join(self.title), " "]
            self.title = []

    def damage(self) -> None:
        if self.verse is not None and self.book is not None:
            self.out.damaged.add((self.book, self.chapter, self.verse[0]))

    def flush(self) -> None:
        if self.verse is not None and self.book is not None:
            key = (self.book, self.chapter, self.verse[0])
            text = _clean("".join(self.parts))
            if key in self.out.verses:
                text = f"{self.out.verses[key]} {text}".strip()
            self.out.verses[key] = text
        self.verse = None
        self.parts = []

    def close(self) -> None:
        self.end_block()
        self.flush()
        super().close()


def _clean(text: str) -> str:
    return _WS.sub(" ", text.replace("*", "")).strip()


def parse_epub(
    path: Path, seeds: list[BookSeed], skeleton: dict[tuple[str, int], int]
) -> EpubBible:
    """Read ``path`` (an EPUB) into verses and headings keyed by USFM code."""
    with zipfile.ZipFile(path) as archive:
        reader = _Reader(seeds, skeleton)
        for name in spine_documents(archive):
            if not name.endswith((".html", ".xhtml", ".htm")):
                continue
            reader.feed(archive.read(name).decode("utf-8", errors="replace"))
            reader.end_block()
        reader.close()
    return reader.out
