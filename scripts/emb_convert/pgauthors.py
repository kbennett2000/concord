"""Personal Gold's author notes and credits as one document (V8-S5c; docs/v8/SPEC.md §4.3).

Two lists print together in the feature region, before the Personal Gold articles (S3a), and
make one ``about`` document, as printed:

- the **author index** (its outline section): a head (the feature's name), a small subtitle,
  then one paragraph per author: the name in small bold link type — linking to the author's
  article — and the note. ``## <subtitle>``, then ``**Name** note…`` each;
- the **Personal Gold index** (the head of the feature's own section, before its first
  article): a title-size head, then one entry per article: its title in small bold link type,
  the author on the next line and, after a gap, the credit — the book the excerpt is taken
  from. ``## <head>``, then ``**Title**\\`` + the author, and the credit as a paragraph.

**Ties.** S3a pairs each index entry with its article (``Article.entry``), so a credit ties to
the article whose note carries that entry's name as its ``title``. An author note ties to the
article its name links to (that page, or one off) whose index entry prints the same name, and
whose byline holds it; every note must tie to one article, none twice. An article no note names
is listed. The links point into the feature region, not the Bible: none is a ``ref:`` link.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from emb_convert.articles import PG, PG_AUTHORS, PG_LABEL_SIZE, Article, ArticleRegion, IndexEntry
from emb_convert.clean import Fixes
from emb_convert.documents import (
    MARGIN,
    Blocks,
    Witnessed,
    gap,
    hygiene,
    is_title,
    left,
    letters,
)
from emb_convert.layout import Layout, LinkKind
from emb_convert.lines import Line, group_lines
from emb_convert.notes import Context
from emb_convert.notetext import Piece, assemble, plain_text
from emb_convert.pdfxml import PdfDocument, TextItem

KIND = "about"
SLUG = "about-1"
SMALL_SIZE = 9  # a name or a title in the lists
TEXT_SIZE = 12

Key = tuple[str, int, int]


def note_key(n: int) -> Key:
    return (f"PG AUTHOR {n}", 0, 1)


def credit_key(n: int) -> Key:
    return (f"PG CREDIT {n}", 0, 1)


@dataclass(slots=True)
class AuthorNote:
    lines: list[Line]
    name: str
    page: int | None  # the page its name links to
    article: Article | None = None


@dataclass(slots=True)
class Credit:
    title: list[Line]
    author: list[Line]
    credit: list[Line]
    entry: IndexEntry | None = None
    article: Article | None = None

    @property
    def lines(self) -> list[Line]:
        return [*self.title, *self.author, *self.credit]


@dataclass(slots=True)
class AuthorFindings:
    """Personal Gold's author notes and credits (V8-S5c): found, tied, written and checked."""

    document: dict[str, object] | None = None
    notes: list[AuthorNote] = field(default_factory=list[AuthorNote])
    credits: list[Credit] = field(default_factory=list[Credit])
    articles: list[Article] = field(default_factory=list[Article])  # Personal Gold's, in order
    words: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    fixes: Counter[str] = field(default_factory=Counter[str])
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])
    witnessed: Witnessed = field(default_factory=Witnessed)

    @property
    def without_note(self) -> list[tuple[int, Article]]:
        """Articles (numbered in the index's order) no author note names."""
        named = {id(n.article) for n in self.notes if n.article is not None}
        return [(n, a) for n, a in enumerate(self.articles, 1) if id(a) not in named]

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and self.document is not None
            and not any(self.hygiene.values())
            and all(n.article is not None for n in self.notes)
            and all(c.article is not None for c in self.credits)
        )


def _opens(line: Line) -> bool:
    """A name or a title: small bold link type at the margin."""
    first = line.nonblank[0]
    return first.bold and first.blue and first.size == SMALL_SIZE and left(line) <= MARGIN


def _article_head(line: Line) -> bool:
    """A Personal Gold article's head: the feature's name in large link type (S3a)."""
    return any(i.size == PG_LABEL_SIZE and i.blue for i in line.nonblank)


def _name(line: Line) -> str:
    items: list[TextItem] = []
    for item in line.items:
        if item.stripped and not (item.bold and item.blue):
            break
        items.append(item)
    return " ".join("".join(i.text for i in items).split()).rstrip(" ,")


def _lines(doc: PdfDocument, start: int, end: int) -> list[Line]:
    items = [i for i in doc.items if start <= i.page < end]
    return [line for line in group_lines(items) if line.nonblank]


def _bible_links(lines: Sequence[Line], layout: Layout) -> list[Line]:
    return [
        line
        for line in lines
        for i in line.nonblank
        if i.blue and i.link_page is not None and layout.link_kind(i.link_page) is LinkKind.BIBLE
    ]


def build_authors(
    doc: PdfDocument, layout: Layout, region: ArticleRegion, ctx: Context
) -> AuthorFindings:
    """The author index and the Personal Gold index → one document, tied to S3a's articles."""
    found = AuthorFindings(articles=[a for a in region.articles if a.feature is PG])
    authors = next((s for s in region.sections if s.outline == PG_AUTHORS), None)
    index = next((s for s in region.sections if s.feature is PG), None)
    if authors is None or index is None:
        found.errors.append("PG: no author index or no Personal Gold index")
        return found
    author_lines = _lines(doc, authors.start, authors.end)
    index_lines = _lines(doc, index.start, index.end)
    head = next((n for n, line in enumerate(index_lines) if _article_head(line)), len(index_lines))
    index_lines = index_lines[:head]
    for line in _bible_links([*author_lines, *index_lines], layout):
        found.errors.append(f"PG p{line.page} top {line.top}: a link into the Bible")

    def inline(lines: Sequence[Line]) -> list[Piece]:
        return assemble(lines, ctx.vocabulary, Fixes(), found.fixes, repair=ctx.repair, bold=True)

    blocks = Blocks(inline)
    _author_index(found, author_lines, blocks)
    _credits(found, index_lines, blocks)
    _tie(found, region)
    printed = [*author_lines[1:], *index_lines]  # the author index's head is the title
    if not blocks.holds(inline(printed)):
        found.errors.append("PG: its blocks don't hold exactly the text it prints")
    hygiene(found.hygiene, "PG", blocks.text_plain, printed, ctx, blocks.problems)
    for n, note in enumerate(found.notes, 1):
        _witness(found, note_key(n), note.lines, ctx)
    for n, credit in enumerate(found.credits, 1):
        _witness(found, credit_key(n), credit.lines, ctx)
    found.document = {
        "slug": SLUG,
        "kind": KIND,
        "title": PG.label,
        "ordinal": 1,
        "text": blocks.document,
    }
    return found


def _author_index(found: AuthorFindings, lines: list[Line], blocks: Blocks) -> None:
    if not lines or letters(lines[0].text) != letters(PG.label):
        found.errors.append("PG: the author index's head isn't the feature's name")
        return
    subtitle: list[Line] = []
    for line in lines[1:]:
        if _opens(line):
            found.notes.append(AuthorNote([line], _name(line), line.nonblank[0].link_page))
        elif found.notes and all(i.size == TEXT_SIZE for i in line.nonblank):
            note = found.notes[-1]
            if gap(note.lines[-1], line):
                found.errors.append(f"PG p{line.page} top {line.top}: a gap inside an author note")
            note.lines.append(line)
        elif not found.notes and left(line) > MARGIN:
            subtitle.append(line)
        else:
            found.errors.append(
                f"PG p{line.page} top {line.top}: a line the author index doesn't explain"
            )
    if not subtitle:
        found.errors.append("PG: the author index has no subtitle")
        return
    blocks.head(subtitle)
    for note in found.notes:
        blocks.paragraph(note.lines)
        found.words.setdefault("author notes", []).append(len(blocks.plain[-1].split()))


def _credits(found: AuthorFindings, lines: list[Line], blocks: Blocks) -> None:
    if not lines or not is_title(lines[0]):
        found.errors.append("PG: the Personal Gold index has no head")
        return
    for line in lines[1:]:
        if _opens(line):
            found.credits.append(Credit([line], [], []))
            continue
        if not found.credits:
            found.errors.append(f"PG p{line.page} top {line.top}: a line before the first entry")
            continue
        credit = found.credits[-1]
        last = (credit.credit or credit.author or credit.title)[-1]
        if credit.credit or (credit.author and (gap(last, line) or line.page != last.page)):
            credit.credit.append(line)
        else:
            credit.author.append(line)
    blocks.head(lines[:1])
    for credit in found.credits:
        if not credit.author or not credit.credit:
            found.errors.append(
                f"PG p{credit.title[0].page}: an entry without its author or credit"
            )
            continue
        blocks.broken([credit.title, credit.author])
        blocks.paragraph(credit.credit)
        words = len(blocks.plain[-2].split()) + len(blocks.plain[-1].split())
        found.words.setdefault("credits", []).append(words)


def _tie(found: AuthorFindings, region: ArticleRegion) -> None:
    by_entry = {id(a.entry): a for a in found.articles if a.entry is not None}
    entries = region.entries.get(PG.key, [])
    for credit in found.credits:
        title = letters(_name(credit.title[0]))
        page = credit.title[0].nonblank[0].link_page
        matches = [e for e in entries if e.page == page and letters(e.name) == title]
        if len(matches) != 1:
            found.errors.append(f"PG p{credit.title[0].page}: a credit no index entry pairs with")
            continue
        credit.entry = matches[0]
        credit.article = by_entry.get(id(matches[0]))
        if credit.article is None:
            found.errors.append(f"PG p{credit.title[0].page}: a credit for no article")
    taken: set[int] = set()
    for note in found.notes:
        name = letters(note.name)
        near = [
            a
            for a in found.articles
            if note.page is not None
            and abs(a.page - note.page) <= 1
            and a.entry is not None
            and a.entry.credit
            and letters(a.entry.credit[0].text) == name
            and name in letters(a.byline)
        ]
        if len(near) != 1 or id(near[0]) in taken:
            found.errors.append(f"PG p{note.lines[0].page}: an author note no one article ties to")
            continue
        note.article = near[0]
        taken.add(id(near[0]))


def _witness(found: AuthorFindings, k: Key, lines: list[Line], ctx: Context) -> None:
    scratch: Counter[str] = Counter()

    def plain(fixes: Fixes) -> str:
        pieces = assemble(lines, ctx.vocabulary, fixes, scratch, repair=ctx.repair, bold=True)
        return plain_text(pieces)

    found.witnessed.add(k, lines, plain)
