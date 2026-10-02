"""The feature articles: Men, Women, and God; Someone You Should Know; Personal Gold (V8-S3a).

Each feature has a section of its own after the textual notes (``layout.features_start``),
found by its index's outline entry and running to the next entry. A section opens with its
index — the book's own name for every article and the page it starts on — and then prints
the articles:

- **Men, Women, and God**: a bold size-15 title (it may wrap), then the passage in size 7.
- **Someone You Should Know**: a blue "…:" link back to the index and the person's name in
  bold, then the passage in size 7.
- **Personal Gold**: the feature's name in size 23 linking to its index, "from" and the
  author (linking to the author index), the passage in size 12, the title in size-15 capitals.

The Bible text calls each article out with a callout line (``text.FeatureCallout``): a bold
blue label — the article's name in its index — linking to its page. A callout matches the one
article of its feature on its target page (±1) whose index name is the label. An article
anchors at its callout: at the **end** of the verse the line follows when the line comes after
the article's first verse in that book (Men, Women, and God and Personal Gold close their
passage), else at the **start** of the verse it precedes (Someone You Should Know opens it, a
book introduction's callout stands before 1:1). One the book never calls out anchors at the
start of its first passage. Nothing here holds book text: it is read from the operator's PDF.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from bible_core.normalize import normalize

from emb_convert.layout import Layout
from emb_convert.lines import Line, group_lines
from emb_convert.pdfxml import PdfDocument, TextItem
from emb_convert.study import SINGLE_CHAPTER, Part, parse_parts
from emb_convert.text import FeatureCallout

TITLE_SIZE = 15
PG_LABEL_SIZE = 23
REFERENCE_SIZE = 7
INDEX_SUFFIX = " Index"

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class Feature:
    key: str  # short name in the summary and the cross-check keys
    outline: str  # the outline title of its index; the label is this minus " Index"
    head: str  # "title" (MWG) · "name" (SYSK) · "label" (PG): how an article opens

    @property
    def label(self) -> str:
        return self.outline.removesuffix(INDEX_SUFFIX)


MWG = Feature("MWG", "Men, Women, and God Index", "title")
SYSK = Feature("SYSK", "Someone You Should Know Index", "name")
PG = Feature("PG", "Personal Gold Index", "label")
FEATURES = (MWG, SYSK, PG)
PG_AUTHORS = "Personal Gold Author Index"


class ArticleError(Exception):
    """The feature region is not shaped as expected."""


@dataclass(frozen=True, slots=True)
class Section:
    feature: Feature | None  # None: a section this slice doesn't read (WBSA, charts, …)
    outline: str
    start: int
    end: int  # exclusive

    def holds(self, page: int) -> bool:
        return self.start <= page < self.end


@dataclass(slots=True)
class IndexEntry:
    name: str  # the index's name for the article
    page: int  # the page its link targets
    reference: str = ""  # Men, Women, and God's index prints the passage too
    credit: list[Line] = field(default_factory=list[Line])  # Personal Gold: author + source


@dataclass(slots=True)
class Article:
    feature: Feature
    page: int
    printed: str  # its heading as the article prints it
    reference: str  # the passage as printed, broken words joined
    parts: list[tuple[str, Part]]  # (book, part), in the reference's order
    lines: list[Line]  # the body
    byline: str = ""  # Personal Gold: the author as printed
    entry: IndexEntry | None = None  # its index entry
    callouts: list[FeatureCallout] = field(default_factory=list[FeatureCallout])

    @property
    def title(self) -> str:
        return self.entry.name if self.entry is not None else self.printed

    @property
    def books(self) -> list[str]:
        return list(dict.fromkeys(book for book, _ in self.parts))

    def parts_in(self, book: str) -> list[Part]:
        return [part for b, part in self.parts if b == book]


@dataclass(slots=True)
class ArticleRegion:
    sections: list[Section] = field(default_factory=list[Section])
    entries: dict[str, list[IndexEntry]] = field(default_factory=dict[str, list[IndexEntry]])
    articles: list[Article] = field(default_factory=list[Article])
    authors: int = 0  # Personal Gold author notes (for V8-S5)
    unmatched_callouts: list[FeatureCallout] = field(default_factory=list[FeatureCallout])
    other_callouts: dict[str, int] = field(default_factory=dict[str, int])  # by section outline
    unindexed: list[Article] = field(default_factory=list[Article])
    renamed: list[Article] = field(default_factory=list[Article])  # index words its name otherwise
    errors: list[str] = field(default_factory=list[str])
    m_breaks: int = 0  # reference-font words broken after "m", joined


def sections(doc: PdfDocument, layout: Layout) -> list[Section]:
    """The feature region's sections, one per outline entry, in page order."""
    entries = sorted(
        (e for e in doc.outline if layout.features_start <= e.page < layout.study_start),
        key=lambda e: e.page,
    )
    by_outline = {f.outline: f for f in FEATURES}
    out: list[Section] = []
    for n, entry in enumerate(entries):
        end = entries[n + 1].page if n + 1 < len(entries) else layout.study_start
        out.append(Section(by_outline.get(entry.title), entry.title, entry.page, end))
    missing = [f.outline for f in FEATURES if not any(s.feature is f for s in out)]
    if missing:
        raise ArticleError(f"outline lacks the feature index {missing[0]!r}")
    return out


def section_of(sections_: Sequence[Section], page: int) -> Section | None:
    return next((s for s in sections_ if s.holds(page)), None)


# --- references ----------------------------------------------------------------------------

_M_BREAK = re.compile(r"(?<=m) (?=[a-z])")  # the size-7 font breaks a word after "m"
_BOOK = re.compile(r"^(Book of )?((?:[1-3] )?[A-Z][a-z]+(?: of [A-Z][a-z]+)?)(?: (.*))?$")
_CHAPTERS = re.compile(r"^chapters? (.*)$")
_CHAPTER_RANGE = re.compile(r"^(\d+)(?:-(\d+))?$")
_SPLIT = re.compile(r"\s*;\s*|\s+and\s+")


def parse_reference(
    text: str, by_alias: dict[str, str], last_verse: dict[tuple[str, int], int]
) -> list[tuple[str, Part]] | str:
    """An article's printed passage → (book, part)s, or an error message.

    ``Genesis 1:27 and 2:15-25`` · ``Genesis 12:10-20 and chapter 20`` · ``Leviticus 18;
    Deuteronomy 22:13-30`` · ``Judges 4–5`` · ``Book of Esther`` · ``Acts 18:1-3, 24-26;
    21:8-9``. A chapter alone is the whole chapter, written with its last verse; a book alone
    is the whole book.
    """
    text = text.replace("–", "-").replace("—", "-")
    parts: list[tuple[str, Part]] = []
    book: str | None = None
    for group in _SPLIT.split(text.strip()):
        match = _BOOK.match(group)
        named = by_alias.get(normalize(match.group(2))) if match else None
        if match is not None and named is not None:
            book, group = named, match.group(3) or ""
            if match.group(1) or not group:  # "Book of Esther": all of it
                chapters = sorted(c for b, c in last_verse if b == book)
                if not chapters:
                    return f"{text!r}: no chapters for {book}"
                parts.append((book, Part(1, 1, chapters[-1], last_verse[(book, chapters[-1])])))
                continue
        if book is None:
            return f"{text!r}: no book before {group!r}"
        words = _CHAPTERS.match(group)
        numbers = words.group(1) if words else group
        whole = _CHAPTER_RANGE.match(numbers)
        if whole is not None and (words is not None or ":" not in numbers):
            if book in SINGLE_CHAPTER and words is None:
                found = parse_parts(book, numbers)
            else:
                first, last = int(whole.group(1)), int(whole.group(2) or whole.group(1))
                if (book, last) not in last_verse or first > last:
                    return f"{text!r}: chapter {numbers} is not in {book}"
                found = [Part(first, 1, last, last_verse[(book, last)])]
        else:
            found = parse_parts(book, numbers.replace(" ", ""))
        if isinstance(found, str):
            return found
        parts += [(book, part) for part in found]
    if not parts:
        return f"{text!r}: no passage"
    return parts


def join_m_breaks(text: str) -> tuple[str, int]:
    joined, count = _M_BREAK.subn("", text)
    return joined, count


# --- the index -----------------------------------------------------------------------------


def _text(items: Sequence[TextItem]) -> str:
    return " ".join("".join(i.text for i in items).split())


def _entries(feature: Feature, lines: list[Line], section: Section) -> list[IndexEntry]:
    """The index lines (before the first article) → its entries."""
    entries: list[IndexEntry] = []
    for line in lines:
        content = line.nonblank
        first = content[0]
        target = first.link_page if first.blue else None
        if target is not None and section.holds(target) and target != section.start:
            names = [i for i in content if i.blue and i.link_page == target]
            rest = [i for i in content if not (i.blue and i.link_page == target)]
            entry = IndexEntry(_text(names).rstrip(" ."), target)
            if feature is MWG:
                entry.reference = _text([i for i in rest if i.blue])
            entries.append(entry)
        elif entries and feature is MWG:
            entries[-1].reference = " ".join(
                [entries[-1].reference, _text([i for i in content if i.blue])]
            ).strip()
        elif entries and feature is PG:
            entries[-1].credit.append(line)
    return entries


# --- the articles --------------------------------------------------------------------------


def _all(content: Sequence[TextItem], size: int, *, bold: bool = True) -> bool:
    return all(i.size == size and (i.bold or not bold) for i in content)


def _head_at(feature: Feature, lines: list[Line], n: int, section: Section) -> bool:
    content = lines[n].nonblank
    if feature is MWG:
        before = lines[n - 1].nonblank if n else []
        if not _all(content, TITLE_SIZE) or (before and _all(before, TITLE_SIZE)):
            return False
        k = n + 1  # a title (it may wrap) over its passage — not the index's own header
        while k < len(lines) and _all(lines[k].nonblank, TITLE_SIZE):
            k += 1
        return k < len(lines) and _all(lines[k].nonblank, REFERENCE_SIZE, bold=False)
    if feature is SYSK:
        first = content[0]
        return first.blue and first.link_page == section.start and any(i.bold for i in content)
    return any(i.size == PG_LABEL_SIZE and i.blue for i in content)


def _reference_line(line: Line) -> str:
    return _text(line.nonblank)


def parse_articles(
    doc: PdfDocument,
    layout: Layout,
    by_alias: dict[str, str],
    last_verse: dict[tuple[str, int], int],
) -> ArticleRegion:
    """Every article of the three features, with its index entry."""
    region = ArticleRegion(sections=sections(doc, layout))
    for section in region.sections:
        lines = [
            line
            for line in group_lines([i for i in doc.items if section.holds(i.page)])
            if line.nonblank
        ]
        if section.outline == PG_AUTHORS:
            region.authors = sum(
                1 for line in lines if line.nonblank[0].blue and line.nonblank[0].bold
            )
            continue
        feature = section.feature
        if feature is None:
            continue
        heads = [n for n in range(len(lines)) if _head_at(feature, lines, n, section)]
        index_end = heads[0] if heads else len(lines)
        entries = _entries(feature, lines[:index_end], section)
        region.entries[feature.key] = entries
        for k, at in enumerate(heads):
            end = heads[k + 1] if k + 1 < len(heads) else len(lines)
            article = _article(feature, lines[at:end], by_alias, last_verse, region)
            if article is not None:
                region.articles.append(article)
        _index(feature, entries, [a for a in region.articles if a.feature is feature], region)
    return region


def _article(
    feature: Feature,
    lines: list[Line],
    by_alias: dict[str, str],
    last_verse: dict[tuple[str, int], int],
    region: ArticleRegion,
) -> Article | None:
    head = lines[0]
    where = f"{feature.key} p{head.page}"
    if feature is MWG:
        title = [head]
        k = 1
        while k < len(lines) and _all(lines[k].nonblank, TITLE_SIZE):
            title.append(lines[k])
            k += 1
        printed = " ".join(_text(line.nonblank) for line in title)
        reference_line, body, byline = lines[k], lines[k + 1 :], ""
    elif feature is SYSK:
        printed = _text([i for i in head.nonblank if i.bold])
        reference_line, body, byline = lines[1], lines[2:], ""
    else:
        byline = _text([i for i in lines[1].nonblank if i.blue])
        reference_line = lines[2]
        k = 3
        title: list[Line] = []
        while k < len(lines) and _all(lines[k].nonblank, TITLE_SIZE):
            title.append(lines[k])
            k += 1
        printed = " ".join(_text(line.nonblank) for line in title)
        body = lines[k:]
    raw = _reference_line(reference_line)
    reference, breaks = join_m_breaks(raw)
    region.m_breaks += breaks
    parts = parse_reference(reference, by_alias, last_verse)
    if isinstance(parts, str):
        region.errors.append(f"{where}: reference {parts}")
        return None
    if not printed or not body:
        region.errors.append(f"{where}: no heading or no text")
        return None
    return Article(feature, head.page, printed, reference, parts, body, byline)


def _one(named: list[_T], exact: list[_T]) -> _T | None:
    """The one candidate its name picks, else the one at exactly its page."""
    if len(named) == 1:
        return named[0]
    if not named and len(exact) == 1:
        return exact[0]
    return None


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _index(
    feature: Feature, entries: list[IndexEntry], articles: list[Article], region: ArticleRegion
) -> None:
    """Pair each article with its index entry: the entry links to its page (±1 — a link can
    land on the page before, where the article's banner sits) and names it as it prints, or
    is the one entry linking to exactly its page (the index can word a name differently:
    it tells two people of one name apart)."""
    free = list(entries)
    for article in articles:
        near = [e for e in free if abs(e.page - article.page) <= 1]
        found = _one(
            [e for e in near if _key(e.name) == _key(article.printed)],
            [e for e in near if e.page == article.page],
        )
        if found is None:
            region.unindexed.append(article)
            continue
        if _key(found.name) != _key(article.printed):
            region.renamed.append(article)
        article.entry = found
        free.remove(found)
    for entry in free:
        region.errors.append(f"{feature.key}: index entry on p{entry.page} names no article")


# --- callouts and anchors ------------------------------------------------------------------


def assign_callouts(region: ArticleRegion, callouts: list[FeatureCallout]) -> None:
    """Give each callout line to the article it names: of its feature, on its target page
    (±1), whose index name (or printed name) is its label — or the one starting on exactly
    its target page."""
    for callout in callouts:
        section = section_of(region.sections, callout.target_page)
        if section is None or section.feature is None:
            key = section.outline if section is not None else "outside the features"
            region.other_callouts[key] = region.other_callouts.get(key, 0) + 1
            continue
        near = [
            a
            for a in region.articles
            if a.feature is section.feature and abs(a.page - callout.target_page) <= 1
        ]
        found = _one(
            [a for a in near if _key(callout.label) in (_key(a.title), _key(a.printed))],
            [a for a in near if a.page == callout.target_page],
        )
        if found is None:
            region.unmatched_callouts.append(callout)
            continue
        found.callouts.append(callout)


@dataclass(frozen=True, slots=True)
class Anchor:
    book: str
    chapter: int
    verse: int  # a number the verse text is stored under
    at_end: bool  # at the end of the verse (char_offset = its length), else at its start
    callout: FeatureCallout | None  # None: never called out — the first passage's start
    outside: bool  # the anchor verse lies outside the article's passages


def anchors(article: Article, stored: dict[tuple[str, int, int], int]) -> list[Anchor] | str:
    """Where the article's notes go: one per callout, or one at its first passage."""

    def verse_of(book: str, chapter: int, verse: int) -> int:
        return stored.get((book, chapter, verse), verse)

    def covered(book: str, chapter: int, verse: int) -> bool:
        return any(
            (p.start_chapter, p.start_verse) <= (chapter, verse) <= (p.end_chapter, p.end_verse)
            for p in article.parts_in(book)
        )

    if not article.callouts:
        book, part = article.parts[0]
        verse = verse_of(book, part.start_chapter, part.start_verse)
        return [Anchor(book, part.start_chapter, verse, False, None, False)]
    out: list[Anchor] = []
    for callout in article.callouts:
        parts = article.parts_in(callout.book)
        if not parts:
            return f"called out in {callout.book}, which its passage doesn't name"
        first = min((p.start_chapter, p.start_verse) for p in parts)
        if callout.after is not None and callout.after >= first:
            chapter, verse = callout.after
            at_end = True
            book = callout.book
        elif callout.before is not None and callout.before[0] == callout.book:
            book, chapter, verse = callout.before
            at_end = False
        else:
            return f"callout on p{callout.page} has no verse after it in {callout.book}"
        stored_verse = verse_of(book, chapter, verse)
        out.append(
            Anchor(book, chapter, stored_verse, at_end, callout, not covered(book, chapter, verse))
        )
    return out


def shape(article: Article, last_verse: dict[tuple[str, int], int]) -> str:
    """two books · multi-part · whole book · whole chapters · cross-chapter · whole chapter ·
    verse · range (they don't overlap)."""
    if len(article.books) > 1:
        return "two books"
    if len(article.parts) > 1:
        return "multi-part"
    book, part = article.parts[0]
    ends_chapter = part.end_verse == last_verse.get((book, part.end_chapter))
    if part.start_chapter != part.end_chapter:
        chapters = [c for b, c in last_verse if b == book]
        if part.start_verse == 1 and ends_chapter:
            if part.start_chapter == 1 and part.end_chapter == max(chapters):
                return "whole book"
            return "whole chapters"
        return "cross-chapter"
    if part.start_verse == part.end_verse:
        return "verse"
    if part.start_verse == 1 and ends_chapter:
        return "whole chapter"
    return "range"


def cross_references(
    article: Article, book: str, last_verse: dict[tuple[str, int], int]
) -> list[dict[str, int | str]]:
    """The article's passages in other books than ``book``, one chapter each (the notes
    contract's ``cross_references`` hold one chapter)."""
    out: list[dict[str, int | str]] = []
    for other, part in article.parts:
        if other == book:
            continue
        for chapter in range(part.start_chapter, part.end_chapter + 1):
            first = part.start_verse if chapter == part.start_chapter else 1
            last = (
                part.end_verse
                if chapter == part.end_chapter
                else last_verse.get((other, chapter), part.end_verse)
            )
            out.append({"book": other, "chapter": chapter, "verse_start": first, "verse_end": last})
    return out
