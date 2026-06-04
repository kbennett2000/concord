"""Pydantic v2 response models — the byte-precise SPEC §7 shapes.

Field declaration order is significant: it is the JSON key order clients encode against.
Parallel and grouped are structurally different (the ``translations`` field is a list vs.
a dict, and verse objects differ), so they are separate models; the endpoint dispatches
on ``?format=``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParallelVerse(BaseModel):
    """One verse position with each requested translation's text (``null`` if omitted)."""

    book: str
    chapter: int
    verse: int
    reference: str
    text: dict[str, str | None]


class VerseResponseParallel(BaseModel):
    """Default shape: one object per verse, translations nested under each."""

    reference: str
    translations: list[str]
    verses: list[ParallelVerse]


class GroupedVerse(BaseModel):
    """One verse under a single translation's list (only verses present in it appear)."""

    book: str
    chapter: int
    verse: int
    text: str


class VerseResponseGrouped(BaseModel):
    """``?format=grouped``: verses bucketed by translation id."""

    reference: str
    translations: dict[str, list[GroupedVerse]]


class SearchHit(BaseModel):
    """One full-text search match with its highlighted snippet."""

    book: str
    chapter: int
    verse: int
    reference: str
    snippet: str


class SearchResponse(BaseModel):
    """A page of search results: the echoed query state, total count, and hits."""

    query: str
    translation: str
    book: str | None
    limit: int
    offset: int
    total: int
    hits: list[SearchHit]


class CrossRefSource(BaseModel):
    """The source verse of a cross-reference (the verse the user asked about)."""

    book: str
    chapter: int
    verse: int
    reference: str


class CrossRefTarget(BaseModel):
    """The target verse (or same-chapter range) a cross-reference points to."""

    book: str
    chapter: int
    verse_start: int
    verse_end: int | None
    reference: str


class CrossRefEntry(BaseModel):
    """One cross-reference. ``text`` is the target's text (null when not requested or
    missing in the chosen translation)."""

    from_: CrossRefSource = Field(serialization_alias="from")
    to: CrossRefTarget
    votes: int | None
    text: str | None


class CrossRefResponse(BaseModel):
    """A page of cross-references for a reference.

    ``translation`` is null unless ``include_text=true`` (in which case a null entry
    ``text`` means the target verse is missing in that translation)."""

    reference: str
    translation: str | None
    min_votes: int
    limit: int
    offset: int
    total: int
    cross_references: list[CrossRefEntry]


class Book(BaseModel):
    """A book's catalog metadata."""

    id: str
    name: str
    testament: str
    chapter_count: int | None
    canonical_order: int


class BooksResponse(BaseModel):
    """The full 66-book catalog, in canonical order."""

    books: list[Book]


class Translation(BaseModel):
    """A loaded translation's catalog metadata."""

    id: str
    name: str
    language: str
    versification: str
    attribution: str | None


class TranslationsResponse(BaseModel):
    """All loaded translations."""

    translations: list[Translation]


class RandomVerse(BaseModel):
    """The verse returned by /random."""

    book: str
    chapter: int
    verse: int
    reference: str
    text: str


class RandomResponse(BaseModel):
    """A randomly selected verse, echoing the filters that were applied."""

    translation: str
    book: str | None
    testament: str | None
    verse: RandomVerse
