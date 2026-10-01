"""Where things are in the book: book page ranges and what each link target means.

Nothing here is a hard-coded page number. The outline gives each book's first page; the first
"… Textual Notes" header after Revelation's start ends the Bible text; the outline entries
after that mark the feature region and the study notes. A link's target page then says what
kind of link it is (a ``*`` goes to a textual note, a callout to a feature, a blue verse
number to its study note).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from bible_core.normalize import normalize
from bible_core.seed import BookSeed, load_canonical_books_text, parse_canonical_books

from emb_convert.pdfxml import PdfDocument

CHAPTER_NUMBER_SIZE = 23
TEXTUAL_NOTES_SUFFIX = "Textual Notes"
STUDY_NOTES_PREFIX = "Study Notes"


class LayoutError(Exception):
    """The PDF's outline or regions are not shaped as expected."""


class LinkKind(Enum):
    FRONT = "front"
    BIBLE = "bible"
    TEXTUAL_NOTE = "textual-note"
    FEATURE = "feature"
    STUDY_NOTE = "study-note"


@dataclass(frozen=True, slots=True)
class BookRange:
    code: str
    name: str
    order: int
    start_page: int
    end_page: int  # exclusive


@dataclass(frozen=True, slots=True)
class Layout:
    books: list[BookRange]
    bible_start: int
    notes_start: int
    features_start: int
    study_start: int

    def link_kind(self, page: int) -> LinkKind:
        if page < self.bible_start:
            return LinkKind.FRONT
        if page < self.notes_start:
            return LinkKind.BIBLE
        if page < self.features_start:
            return LinkKind.TEXTUAL_NOTE
        if page < self.study_start:
            return LinkKind.FEATURE
        return LinkKind.STUDY_NOTE

    def book_at(self, page: int) -> BookRange | None:
        for book in self.books:
            if book.start_page <= page < book.end_page:
                return book
        return None


def canonical_books() -> list[BookSeed]:
    return parse_canonical_books(load_canonical_books_text())


def find_layout(doc: PdfDocument, seeds: list[BookSeed] | None = None) -> Layout:
    """Locate the 66 books and the note/feature regions, or fail loudly."""
    seeds = seeds if seeds is not None else canonical_books()
    by_alias = {alias: seed for seed in seeds for alias in seed.aliases}

    starts: list[tuple[int, BookSeed]] = []
    for entry in doc.outline:
        seed = by_alias.get(normalize(entry.title))
        if seed is not None:
            starts.append((entry.page, seed))
    found = [seed.id for _, seed in starts]
    expected = [seed.id for seed in sorted(seeds, key=lambda s: s.canonical_order)]
    if found != expected:
        raise LayoutError(
            f"outline books {found[:3]}…({len(found)}) do not match the 66-book canon in order"
        )
    if [page for page, _ in starts] != sorted(page for page, _ in starts):
        raise LayoutError("outline book pages are not ascending")

    last_start = starts[-1][0]
    notes_start = next(
        (
            item.page
            for item in doc.items
            if item.page > last_start
            and item.size == CHAPTER_NUMBER_SIZE
            and item.stripped.endswith(TEXTUAL_NOTES_SUFFIX)
        ),
        None,
    )
    if notes_start is None:
        raise LayoutError(f"no '{TEXTUAL_NOTES_SUFFIX}' header after the last book's start")

    later = sorted(entry.page for entry in doc.outline if entry.page >= notes_start)
    study = [e.page for e in doc.outline if e.title.startswith(STUDY_NOTES_PREFIX)]
    if not later or not study:
        raise LayoutError("outline lacks the feature indexes or the study-notes index")
    features_start, study_start = later[0], study[0]
    if not notes_start < features_start < study_start:
        raise LayoutError(
            f"regions out of order: notes {notes_start}, features {features_start}, "
            f"study notes {study_start}"
        )

    books = [
        BookRange(
            code=seed.id,
            name=seed.name,
            order=seed.canonical_order,
            start_page=page,
            end_page=starts[i + 1][0] if i + 1 < len(starts) else notes_start,
        )
        for i, (page, seed) in enumerate(starts)
    ]
    return Layout(
        books=books,
        bible_start=starts[0][0],
        notes_start=notes_start,
        features_start=features_start,
        study_start=study_start,
    )
