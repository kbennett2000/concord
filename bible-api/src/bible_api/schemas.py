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


class NoteCrossReference(BaseModel):
    """A cross-reference carried by a translator's note → a target verse or range."""

    to_book: str
    to_chapter: int
    to_verse_start: int
    to_verse_end: int | None
    reference: str


class TranslatorNote(BaseModel):
    """One translator's note: its canonical anchor, the point ``char_offset`` a client uses to
    place the marker, and the note's own cross-references."""

    book: str
    chapter: int
    verse: int
    reference: str
    type: str | None
    text: str
    char_offset: int
    marker: str | None
    ordinal: int
    cross_references: list[NoteCrossReference]


class NotesResponse(BaseModel):
    """A passage's translator's notes. ``verse`` echoes the ``?verse`` filter (null when the
    whole chapter was requested). A known translation with no notes returns ``notes: []`` (200),
    not an error — the published image ships zero notes."""

    translation: str
    book: str
    chapter: int
    verse: int | None
    total: int
    notes: list[TranslatorNote]


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


class SemanticSearchHit(BaseModel):
    """One semantic match: its position, cosine score, and text in the display translation.

    ``text`` is ``null`` when ``include_text=false`` or the verse is absent in the requested
    translation (versification differences) — the match still ranks, only its text is null.
    """

    book: str
    chapter: int
    verse: int
    reference: str
    score: float
    text: str | None


class SemanticSearchResponse(BaseModel):
    """Ranked semantic-search results, searched in WEB space, displayed in ``translation``."""

    query: str
    translation: str
    count: int
    results: list[SemanticSearchHit]


class PlaceSummary(BaseModel):
    """A place's summary (SPEC v3 §7). Coordinates are surfaced as named ``latitude`` /
    ``longitude`` — never an ordered pair — and are ``null`` (with ``confidence`` null) for
    unknown/symbolic/multiple places: the honesty model, surfaced rather than hidden."""

    id: str
    friendly_id: str
    name: str
    type: str
    latitude: float | None
    longitude: float | None
    confidence: str | None
    confidence_score: int | None
    status: str


class PlacesResponse(BaseModel):
    """A page of places: the echoed filter/pagination state, total count, and summaries."""

    type: str | None
    status: str | None
    q: str | None
    limit: int
    offset: int
    total: int
    places: list[PlaceSummary]


class PlaceDetail(BaseModel):
    """A single place's full detail: every column plus its verse count."""

    id: str
    friendly_id: str
    name: str
    url_slug: str
    type: str
    preceding_article: str
    latitude: float | None
    longitude: float | None
    confidence: str | None
    confidence_score: int | None
    status: str
    modern_name: str | None
    verse_count: int


class PlaceVerse(BaseModel):
    """One verse a place is mentioned in. ``text`` is null when not requested or absent."""

    book: str
    chapter: int
    verse: int
    reference: str
    text: str | None


class PlaceVersesResponse(BaseModel):
    """A page of the verses mentioning a place, echoing the request state.

    ``translation`` is null unless ``include_text=true``."""

    id: str
    translation: str | None
    include_text: bool
    limit: int
    offset: int
    total: int
    verses: list[PlaceVerse]


class VersePlacesResponse(BaseModel):
    """The places named in a verse or range (the inverse lookup): the full deduped union."""

    reference: str
    total: int
    places: list[PlaceSummary]
