"""Verse/chapter queries over the loaded corpus.

Pure data access: takes a SQLite connection + structured input and returns flat
``VerseRow`` records the API's shaper turns into parallel or grouped JSON. No web or
Pydantic imports — ``bible-core`` stays standalone (SPEC §2).

Each :class:`~bible_core.parser.Span` maps to **one** SQL query; ranges are expressed as
``BETWEEN`` / linear ``(chapter, verse)`` predicates and never materialized in Python, so
``John 1:1-99999999`` stays one cheap query (the invariant inherited from Slice 3).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .parser import Reference, Span


@dataclass(frozen=True)
class VerseRow:
    """One verse of one translation."""

    book_id: str
    chapter: int
    verse: int
    translation_id: str
    text: str


@dataclass(frozen=True)
class QueryResult:
    """A query's flat rows plus the metadata the shaper needs."""

    reference: str  # canonical top-level reference echo (e.g. "John 3:16-17")
    book_id: str
    book_name: str
    translations: tuple[str, ...]  # requested ids, in requested order
    rows: tuple[VerseRow, ...]


def get_verses(
    conn: sqlite3.Connection, reference: Reference, translation_ids: Sequence[str]
) -> QueryResult:
    """Fetch every verse of ``reference`` for the requested translations."""
    ids = tuple(translation_ids)
    rows = _collect(conn, reference.book_id, reference.spans, ids)
    return QueryResult(
        reference=reference.echo,
        book_id=reference.book_id,
        book_name=reference.book_name,
        translations=ids,
        rows=rows,
    )


def get_chapter(
    conn: sqlite3.Connection,
    book_id: str,
    book_name: str,
    chapter: int,
    translation_ids: Sequence[str],
) -> QueryResult:
    """Fetch a whole chapter for the requested translations."""
    ids = tuple(translation_ids)
    rows = _collect(conn, book_id, (Span(chapter, None, chapter, None),), ids)
    return QueryResult(
        reference=f"{book_name} {chapter}",
        book_id=book_id,
        book_name=book_name,
        translations=ids,
        rows=rows,
    )


def iter_verses(conn: sqlite3.Connection, translation_id: str) -> Iterator[VerseRow]:
    """Yield every verse of ``translation_id`` in canonical order (book, chapter, verse).

    A read-only bulk reader for whole-translation passes (e.g. building the semantic
    embeddings). Streams rows from the cursor, so callers iterate without holding the whole
    corpus in memory unless they choose to materialize it.
    """
    cursor = conn.execute(
        "SELECT v.book_id, v.chapter, v.verse, v.translation_id, v.text "
        "FROM verses v JOIN books b ON b.id = v.book_id "
        "WHERE v.translation_id = ? "
        "ORDER BY b.canonical_order, v.chapter, v.verse",
        (translation_id,),
    )
    for row in cursor:
        yield VerseRow(
            book_id=row["book_id"],
            chapter=row["chapter"],
            verse=row["verse"],
            translation_id=row["translation_id"],
            text=row["text"],
        )


def _collect(
    conn: sqlite3.Connection,
    book_id: str,
    spans: Sequence[Span],
    translation_ids: tuple[str, ...],
) -> tuple[VerseRow, ...]:
    if not translation_ids:
        return ()
    rows: list[VerseRow] = []
    for span in spans:
        rows.extend(_query_span(conn, book_id, span, translation_ids))
    return tuple(rows)


def _span_predicate(span: Span, chapter_col: str, verse_col: str) -> tuple[str, list[int]]:
    """SQL predicate + params matching a Span against the given chapter/verse columns.

    Shared by verse queries (``chapter``/``verse``), cross-ref queries
    (``from_chapter``/``from_verse``), and existence checks — one place defines the
    chapter-mode / same-chapter / cross-chapter linear-range logic.
    """
    if span.start_verse is None:  # whole-chapter / chapter-range
        return f"{chapter_col} BETWEEN ? AND ?", [span.start_chapter, span.end_chapter]
    assert span.end_verse is not None  # parser invariant: verse bounds are set together
    if span.start_chapter == span.end_chapter:  # same-chapter verse range
        return (
            f"{chapter_col} = ? AND {verse_col} BETWEEN ? AND ?",
            [span.start_chapter, span.start_verse, span.end_verse],
        )
    return (  # cross-chapter linear (chapter, verse) range
        f"({chapter_col} > ? OR ({chapter_col} = ? AND {verse_col} >= ?)) "
        f"AND ({chapter_col} < ? OR ({chapter_col} = ? AND {verse_col} <= ?))",
        [
            span.start_chapter,
            span.start_chapter,
            span.start_verse,
            span.end_chapter,
            span.end_chapter,
            span.end_verse,
        ],
    )


def _query_span(
    conn: sqlite3.Connection,
    book_id: str,
    span: Span,
    translation_ids: tuple[str, ...],
) -> list[VerseRow]:
    predicate, span_params = _span_predicate(span, "chapter", "verse")
    placeholders = ",".join("?" for _ in translation_ids)
    params: list[str | int] = [book_id, *span_params, *translation_ids]
    sql = (
        "SELECT book_id, chapter, verse, translation_id, text FROM verses "
        f"WHERE book_id = ? AND {predicate} AND translation_id IN ({placeholders}) "
        "ORDER BY chapter, verse, translation_id"
    )
    return [VerseRow(r[0], r[1], r[2], r[3], r[4]) for r in conn.execute(sql, params)]


def reference_exists(conn: sqlite3.Connection, reference: Reference) -> bool:
    """True if any translation has at least one verse within ``reference`` (bounds check).

    Used by the HTTP layer to distinguish a valid-but-cross-ref-less verse (200) from a
    verse out of canonical range in every translation (404).
    """
    for span in reference.spans:
        predicate, span_params = _span_predicate(span, "chapter", "verse")
        row = conn.execute(
            f"SELECT 1 FROM verses WHERE book_id = ? AND {predicate} LIMIT 1",
            [reference.book_id, *span_params],
        ).fetchone()
        if row is not None:
            return True
    return False


def get_verse_text(
    conn: sqlite3.Connection, translation_id: str, book_id: str, chapter: int, verse: int
) -> str | None:
    """Text of one verse in one translation, or ``None`` if absent there."""
    row = conn.execute(
        "SELECT text FROM verses WHERE translation_id = ? AND book_id = ? "
        "AND chapter = ? AND verse = ?",
        (translation_id, book_id, chapter, verse),
    ).fetchone()
    return None if row is None else row[0]


# --- full-text search (FTS5) ---------------------------------------------------------

# Markers wrapped around matched terms in the snippet (semantic HTML; easy to transform).
SEARCH_MARK_OPEN = "<mark>"
SEARCH_MARK_CLOSE = "</mark>"
SNIPPET_TOKENS = 32  # snippet window; short verses show in full, long ones are windowed


class SearchQueryError(Exception):
    """The FTS5 MATCH expression is malformed (mapped to HTTP 400 by the API)."""


@dataclass(frozen=True)
class SearchHit:
    """One search match: its position, canonical book name, and highlighted snippet."""

    book_id: str
    book_name: str
    chapter: int
    verse: int
    snippet: str


@dataclass(frozen=True)
class SearchPage:
    """A page of hits plus the total match count (for pagination metadata)."""

    hits: tuple[SearchHit, ...]
    total: int


def search_verses(
    conn: sqlite3.Connection,
    query: str,
    translation_id: str,
    book_id: str | None,
    limit: int,
    offset: int,
) -> SearchPage:
    """Full-text search one translation, optionally filtered to one book.

    Relevance-ranked (FTS5 ``rank``) with a canonical tiebreak, so successive
    ``limit``/``offset`` pages don't overlap. Returns the page plus the total match count
    (a second query). Raises :class:`SearchQueryError` if the MATCH expression is invalid.
    """
    book_filter = " AND v.book_id = ?" if book_id is not None else ""
    base_params: list[str] = [query, translation_id]
    if book_id is not None:
        base_params.append(book_id)

    snippet_fn = (
        f"snippet(verses_fts, 0, '{SEARCH_MARK_OPEN}', "
        f"'{SEARCH_MARK_CLOSE}', '…', {SNIPPET_TOKENS})"
    )
    hits_sql = (
        f"SELECT v.book_id, b.name, v.chapter, v.verse, {snippet_fn} "
        "FROM verses_fts f "
        "JOIN verses v ON v.id = f.rowid "
        "JOIN books b ON b.id = v.book_id "
        f"WHERE verses_fts MATCH ? AND v.translation_id = ?{book_filter} "
        "ORDER BY f.rank, b.canonical_order, v.chapter, v.verse "
        "LIMIT ? OFFSET ?"
    )
    count_sql = (
        "SELECT COUNT(*) FROM verses_fts f "
        "JOIN verses v ON v.id = f.rowid "
        f"WHERE verses_fts MATCH ? AND v.translation_id = ?{book_filter}"
    )

    try:
        hit_rows = conn.execute(hits_sql, [*base_params, limit, offset]).fetchall()
        total = conn.execute(count_sql, base_params).fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise SearchQueryError(str(exc)) from exc

    hits = tuple(SearchHit(r[0], r[1], r[2], r[3], r[4]) for r in hit_rows)
    return SearchPage(hits=hits, total=total)


@dataclass(frozen=True)
class VerseMatch:
    """One translation's match for a canonical verse: which translation, and its marked snippet."""

    translation_id: str
    snippet: str


@dataclass(frozen=True)
class MultiSearchHit:
    """A canonical verse that matched in >=1 searched translation, with a match per translation.

    ``matches`` is ordered best-relevance-first, so ``matches[0]`` is the top-ranked translation's
    snippet (the API surfaces it as the flat ``snippet`` for clients that read only that field).
    """

    book_id: str
    book_name: str
    chapter: int
    verse: int
    matches: tuple[VerseMatch, ...]


@dataclass(frozen=True)
class MultiSearchPage:
    """A page of canonical-verse hits plus the total count of distinct matching verses."""

    hits: tuple[MultiSearchHit, ...]
    total: int


def search_verses_multi(
    conn: sqlite3.Connection,
    query: str,
    translation_ids: Sequence[str],
    book_id: str | None,
    limit: int,
    offset: int,
) -> MultiSearchPage:
    """Full-text search across several translations, deduped by **canonical verse**.

    One hit per canonical verse that matched in at least one of ``translation_ids``, ranked by best
    (max) per-verse FTS relevance — ``MIN(f.rank)``, since FTS5 ``rank`` is lower-is-better — with a
    canonical tiebreak, so ``limit``/``offset`` pages over canonical *verses* (not (verse,
    translation) pairs) never overlap. ``total`` counts distinct matching verses.

    Two queries (the ``get_notes`` precedent): query 1 ranks + paginates the canonical verses;
    query 2 hydrates the per-translation snippets for only that page's verses, so snippet work is
    bounded by ``limit × len(translation_ids)`` — no per-verse fan-out. Raises
    :class:`SearchQueryError` on a malformed MATCH. ``translation_ids`` is assumed non-empty and
    validated by the caller.
    """
    placeholders = ",".join("?" * len(translation_ids))
    ids = list(translation_ids)
    book_filter = " AND v.book_id = ?" if book_id is not None else ""
    match_params: list[str] = [query, *ids]
    if book_id is not None:
        match_params.append(book_id)

    page_sql = (
        "SELECT v.book_id, b.name, v.chapter, v.verse, MIN(f.rank) AS best_rank "
        "FROM verses_fts f "
        "JOIN verses v ON v.id = f.rowid "
        "JOIN books b ON b.id = v.book_id "
        f"WHERE verses_fts MATCH ? AND v.translation_id IN ({placeholders}){book_filter} "
        "GROUP BY v.book_id, v.chapter, v.verse "
        "ORDER BY best_rank, b.canonical_order, v.chapter, v.verse "
        "LIMIT ? OFFSET ?"
    )
    count_sql = (
        "SELECT COUNT(*) FROM ("
        "SELECT 1 FROM verses_fts f "
        "JOIN verses v ON v.id = f.rowid "
        f"WHERE verses_fts MATCH ? AND v.translation_id IN ({placeholders}){book_filter} "
        "GROUP BY v.book_id, v.chapter, v.verse)"
    )

    try:
        page_rows = conn.execute(page_sql, [*match_params, limit, offset]).fetchall()
        total = conn.execute(count_sql, match_params).fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise SearchQueryError(str(exc)) from exc

    if not page_rows:
        return MultiSearchPage(hits=(), total=total)

    # Query 2: snippets for just this page's verses. Row-value IN keyed on (book, chapter, verse).
    keys = [(r[0], r[2], r[3]) for r in page_rows]
    key_placeholders = ",".join("(?,?,?)" for _ in keys)
    snippet_fn = (
        f"snippet(verses_fts, 0, '{SEARCH_MARK_OPEN}', "
        f"'{SEARCH_MARK_CLOSE}', '…', {SNIPPET_TOKENS})"
    )
    detail_sql = (
        f"SELECT v.book_id, v.chapter, v.verse, v.translation_id, {snippet_fn} "
        "FROM verses_fts f "
        "JOIN verses v ON v.id = f.rowid "
        f"WHERE verses_fts MATCH ? AND v.translation_id IN ({placeholders}) "
        f"AND (v.book_id, v.chapter, v.verse) IN (VALUES {key_placeholders}) "
        "ORDER BY f.rank, v.translation_id"
    )
    detail_params: list[str | int] = [query, *ids]
    for book, chapter, verse in keys:
        detail_params.extend((book, chapter, verse))

    try:
        detail_rows = conn.execute(detail_sql, detail_params).fetchall()
    except sqlite3.OperationalError as exc:
        raise SearchQueryError(str(exc)) from exc

    by_verse: dict[tuple[str, int, int], list[VerseMatch]] = defaultdict(list)
    for r in detail_rows:
        by_verse[(r[0], r[1], r[2])].append(VerseMatch(r[3], r[4]))

    hits = tuple(
        MultiSearchHit(
            book_id=r[0],
            book_name=r[1],
            chapter=r[2],
            verse=r[3],
            matches=tuple(by_verse[(r[0], r[2], r[3])]),
        )
        for r in page_rows
    )
    return MultiSearchPage(hits=hits, total=total)


# --- cross-references ----------------------------------------------------------------


@dataclass(frozen=True)
class CrossRefRow:
    """One cross-reference: a source verse → a target verse or same-chapter range."""

    from_book_id: str
    from_book_name: str
    from_chapter: int
    from_verse: int
    to_book_id: str
    to_book_name: str
    to_chapter: int
    to_verse_start: int
    to_verse_end: int | None  # None ⇒ single verse (or a clamped multi-chapter target)
    votes: int | None


@dataclass(frozen=True)
class CrossRefPage:
    """A page of cross-references plus the total match count."""

    rows: tuple[CrossRefRow, ...]
    total: int


def get_cross_references(
    conn: sqlite3.Connection,
    reference: Reference,
    min_votes: int,
    limit: int,
    offset: int,
) -> CrossRefPage:
    """Cross-references whose source verse falls within ``reference``, votes ≥ ``min_votes``.

    Ordered by votes desc with a canonical tiebreak (so pages don't overlap); ``total`` is
    a separate count across the whole reference.
    """
    clauses: list[str] = []
    params: list[str | int] = [reference.book_id]
    for span in reference.spans:
        predicate, span_params = _span_predicate(span, "from_chapter", "from_verse")
        clauses.append(f"({predicate})")
        params += span_params
    where = f"from_book_id = ? AND ({' OR '.join(clauses)}) AND votes >= ?"
    params.append(min_votes)

    hits_sql = (
        "SELECT x.from_book_id, bf.name, x.from_chapter, x.from_verse, "
        "x.to_book_id, bt.name, x.to_chapter, x.to_verse_start, x.to_verse_end, x.votes "
        "FROM cross_references x "
        "JOIN books bf ON bf.id = x.from_book_id "
        "JOIN books bt ON bt.id = x.to_book_id "
        f"WHERE {where} "
        "ORDER BY x.votes DESC, bf.canonical_order, x.from_chapter, x.from_verse, "
        "bt.canonical_order, x.to_chapter, x.to_verse_start "
        "LIMIT ? OFFSET ?"
    )
    rows = tuple(
        CrossRefRow(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9])
        for r in conn.execute(hits_sql, [*params, limit, offset])
    )
    total = conn.execute(f"SELECT COUNT(*) FROM cross_references WHERE {where}", params).fetchone()[
        0
    ]
    return CrossRefPage(rows=rows, total=total)


# --- translator's notes (v4) ---------------------------------------------------------


@dataclass(frozen=True)
class NoteCrossRefRow:
    """One cross-reference carried by a note → a target verse or range (canonical coords)."""

    to_book_id: str
    to_book_name: str
    to_chapter: int
    to_verse_start: int
    to_verse_end: int | None  # None ⇒ single verse


@dataclass(frozen=True)
class NoteRow:
    """One translator's note for a passage, with its own cross-references nested."""

    id: int
    book_id: str
    book_name: str
    chapter: int
    verse: int
    note_type: str | None
    text: str
    char_offset: int
    marker: str | None
    ordinal: int
    cross_references: tuple[NoteCrossRefRow, ...]


def get_notes(
    conn: sqlite3.Connection,
    translation_id: str,
    book_id: str,
    chapter: int,
    verse: int | None = None,
) -> tuple[NoteRow, ...]:
    """Notes for a chapter (or one verse) in a translation, ordered verse → ordinal → id.

    Unpaginated — a chapter's notes are bounded (mirrors ``get_places_for_reference``). A
    translation with no notes for the passage simply returns ``()`` — the caller serves that as
    an empty list (200), never a 404.
    """
    params: list[str | int] = [translation_id, book_id, chapter]
    verse_clause = ""
    if verse is not None:
        verse_clause = " AND n.verse = ?"
        params.append(verse)

    note_sql = (
        "SELECT n.id, n.book_id, b.name, n.chapter, n.verse, n.note_type, n.text, "
        "n.char_offset, n.marker, n.ordinal "
        "FROM translator_notes n JOIN books b ON b.id = n.book_id "
        f"WHERE n.translation_id = ? AND n.book_id = ? AND n.chapter = ?{verse_clause} "
        "ORDER BY n.verse, n.ordinal, n.id"
    )
    note_rows = conn.execute(note_sql, params).fetchall()
    if not note_rows:
        return ()

    ids = [r[0] for r in note_rows]
    placeholders = ",".join("?" * len(ids))
    xref_sql = (
        "SELECT x.note_id, x.to_book_id, b.name, x.to_chapter, x.to_verse_start, x.to_verse_end "
        "FROM note_cross_references x JOIN books b ON b.id = x.to_book_id "
        f"WHERE x.note_id IN ({placeholders}) ORDER BY x.note_id, x.id"
    )
    by_note: dict[int, list[NoteCrossRefRow]] = defaultdict(list)
    for r in conn.execute(xref_sql, ids):
        by_note[r[0]].append(NoteCrossRefRow(r[1], r[2], r[3], r[4], r[5]))

    return tuple(
        NoteRow(
            r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], tuple(by_note.get(r[0], ()))
        )
        for r in note_rows
    )


@dataclass(frozen=True)
class SectionHeadingRow:
    """One section heading: the chapter position it precedes (``before_verse``) and its text."""

    book_id: str
    book_name: str
    chapter: int
    before_verse: int
    text: str
    ordinal: int


def get_section_headings(
    conn: sqlite3.Connection,
    translation_id: str,
    book_id: str,
    chapter: int,
) -> tuple[SectionHeadingRow, ...]:
    """Section headings for a chapter in a translation, ordered before_verse → ordinal → id.

    Unpaginated — a chapter's headings are bounded (mirrors ``get_notes``). A translation with no
    headings for the chapter (e.g. BSB) simply returns ``()`` — the caller serves that as an empty
    list (200), never a 404.
    """
    sql = (
        "SELECT h.book_id, b.name, h.chapter, h.before_verse, h.text, h.ordinal "
        "FROM section_headings h JOIN books b ON b.id = h.book_id "
        "WHERE h.translation_id = ? AND h.book_id = ? AND h.chapter = ? "
        "ORDER BY h.before_verse, h.ordinal, h.id"
    )
    rows = conn.execute(sql, (translation_id, book_id, chapter)).fetchall()
    return tuple(SectionHeadingRow(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows)


@dataclass(frozen=True)
class NoteSearchHit:
    """One note-search match: its canonical anchor, owning translation, and highlighted snippet.

    The note's own ``cross_references`` are deliberately omitted (fetch via the passage read);
    search hits stay lean (SPEC v5 §4).
    """

    book_id: str
    book_name: str
    chapter: int
    verse: int
    translation_id: str
    note_type: str | None
    char_offset: int
    marker: str | None
    ordinal: int
    snippet: str


@dataclass(frozen=True)
class NoteSearchPage:
    """A page of note-search hits plus the total match count (for pagination metadata)."""

    hits: tuple[NoteSearchHit, ...]
    total: int


def search_notes(
    conn: sqlite3.Connection,
    query: str,
    translation_id: str | None,
    note_type: str | None,
    book_id: str | None,
    limit: int,
    offset: int,
) -> NoteSearchPage:
    """Full-text search translator-note bodies, optionally filtered by translation/type/book.

    The direct analogue of :func:`search_verses` over the ``notes_fts`` mirror. Relevance-ranked
    (FTS5 ``rank``) with a canonical tiebreak extended by ``ordinal`` so multi-note verses page
    deterministically. Returns the page plus the total match count (a second query). Raises
    :class:`SearchQueryError` if the MATCH expression is invalid. Filters are validated at the
    API edge; an instance with no notes simply matches nothing (an empty page, never an error).
    """
    filters = ""
    base_params: list[str] = [query]
    if translation_id is not None:
        filters += " AND n.translation_id = ?"
        base_params.append(translation_id)
    if note_type is not None:
        filters += " AND n.note_type = ?"
        base_params.append(note_type)
    if book_id is not None:
        filters += " AND n.book_id = ?"
        base_params.append(book_id)

    snippet_fn = (
        f"snippet(notes_fts, 0, '{SEARCH_MARK_OPEN}', '{SEARCH_MARK_CLOSE}', '…', {SNIPPET_TOKENS})"
    )
    hits_sql = (
        f"SELECT n.book_id, b.name, n.chapter, n.verse, n.translation_id, n.note_type, "
        f"n.char_offset, n.marker, n.ordinal, {snippet_fn} "
        "FROM notes_fts f "
        "JOIN translator_notes n ON n.id = f.rowid "
        "JOIN books b ON b.id = n.book_id "
        f"WHERE notes_fts MATCH ?{filters} "
        "ORDER BY f.rank, b.canonical_order, n.chapter, n.verse, n.ordinal, n.id "
        "LIMIT ? OFFSET ?"
    )
    count_sql = (
        "SELECT COUNT(*) FROM notes_fts f "
        "JOIN translator_notes n ON n.id = f.rowid "
        f"WHERE notes_fts MATCH ?{filters}"
    )

    try:
        hit_rows = conn.execute(hits_sql, [*base_params, limit, offset]).fetchall()
        total = conn.execute(count_sql, base_params).fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise SearchQueryError(str(exc)) from exc

    hits = tuple(
        NoteSearchHit(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]) for r in hit_rows
    )
    return NoteSearchPage(hits=hits, total=total)


# --- metadata + random ---------------------------------------------------------------


@dataclass(frozen=True)
class BookMeta:
    """A book's catalog metadata."""

    id: str
    name: str
    testament: str
    canonical_order: int
    chapter_count: int | None


@dataclass(frozen=True)
class TranslationMeta:
    """A loaded translation's catalog metadata."""

    id: str
    name: str
    language: str
    versification: str
    attribution: str | None


@dataclass(frozen=True)
class RandomVerse:
    """One verse picked at random."""

    book_id: str
    book_name: str
    chapter: int
    verse: int
    text: str


def get_books(conn: sqlite3.Connection) -> list[BookMeta]:
    """All books in canonical order."""
    return [
        BookMeta(r[0], r[1], r[2], r[3], r[4])
        for r in conn.execute(
            "SELECT id, name, testament, canonical_order, chapter_count "
            "FROM books ORDER BY canonical_order"
        )
    ]


def get_translations(conn: sqlite3.Connection) -> list[TranslationMeta]:
    """All loaded translations, ordered by id."""
    return [
        TranslationMeta(r[0], r[1], r[2], r[3], r[4])
        for r in conn.execute(
            "SELECT id, name, language, versification, attribution FROM translations ORDER BY id"
        )
    ]


def get_random_verse(
    conn: sqlite3.Connection,
    translation_id: str,
    book_id: str | None,
    testament: str | None,
) -> RandomVerse | None:
    """One random verse in ``translation_id``, optionally filtered by book and/or testament.

    Returns ``None`` when the filters match no verse (e.g. ``book`` and ``testament``
    contradict). ``ORDER BY RANDOM()`` scans the matching rows — fine at this scale.
    """
    clauses = ["v.translation_id = ?"]
    params: list[str] = [translation_id]
    if book_id is not None:
        clauses.append("v.book_id = ?")
        params.append(book_id)
    if testament is not None:
        clauses.append("b.testament = ?")
        params.append(testament)

    row = conn.execute(
        "SELECT v.book_id, b.name, v.chapter, v.verse, v.text "
        "FROM verses v JOIN books b ON b.id = v.book_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY RANDOM() LIMIT 1",
        params,
    ).fetchone()
    return None if row is None else RandomVerse(row[0], row[1], row[2], row[3], row[4])


# --- geography (v3): places + the bi-directional place↔verse link ---------------------


@dataclass(frozen=True)
class PlaceRow:
    """One biblical place. Coordinates/confidence are ``None`` for places with no confident
    location (unknown/symbolic/multiple) — the honesty model (SPEC v3 §6)."""

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


@dataclass(frozen=True)
class PlacePage:
    """A page of places plus the total match count."""

    rows: tuple[PlaceRow, ...]
    total: int


@dataclass(frozen=True)
class PlaceVerseRef:
    """One verse a place is mentioned in (book id + name for reference formatting)."""

    book_id: str
    book_name: str
    chapter: int
    verse: int


# The places columns, in schema order; bare and ``p.``-prefixed (for the join query).
_PLACE_COLS = (
    "id",
    "friendly_id",
    "name",
    "url_slug",
    "type",
    "preceding_article",
    "latitude",
    "longitude",
    "confidence",
    "confidence_score",
    "status",
    "modern_name",
)
_PLACE_SELECT = ", ".join(_PLACE_COLS)


def _row_to_place(r: sqlite3.Row) -> PlaceRow:
    return PlaceRow(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11])


def list_places(
    conn: sqlite3.Connection,
    type_filter: str | None,
    status_filter: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> PlacePage:
    """Browse places, optionally filtered by ``type``/``status``/name substring (``q``).

    Ordered ``name, id`` (a stable tiebreak so same-named places paginate deterministically);
    ``total`` is a separate count over the same filter.
    """
    clauses: list[str] = []
    params: list[str] = []
    if type_filter is not None:
        clauses.append("type = ?")
        params.append(type_filter)
    if status_filter is not None:
        clauses.append("status = ?")
        params.append(status_filter)
    if q is not None and q.strip():
        clauses.append("name LIKE '%' || ? || '%'")  # case-insensitive for ASCII names
        params.append(q.strip())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = tuple(
        _row_to_place(r)
        for r in conn.execute(
            f"SELECT {_PLACE_SELECT} FROM places{where} ORDER BY name, id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
    )
    total = conn.execute(f"SELECT COUNT(*) FROM places{where}", params).fetchone()[0]
    return PlacePage(rows=rows, total=total)


def get_place(conn: sqlite3.Connection, place_id: str) -> PlaceRow | None:
    """One place by its stable id, or ``None`` if no such place."""
    row = conn.execute(f"SELECT {_PLACE_SELECT} FROM places WHERE id = ?", (place_id,)).fetchone()
    return None if row is None else _row_to_place(row)


def count_place_verses(conn: sqlite3.Connection, place_id: str) -> int:
    """How many verses mention this place."""
    return conn.execute(
        "SELECT COUNT(*) FROM place_verses WHERE place_id = ?", (place_id,)
    ).fetchone()[0]


def get_place_verses(
    conn: sqlite3.Connection, place_id: str, limit: int, offset: int
) -> tuple[tuple[PlaceVerseRef, ...], int]:
    """The verses mentioning ``place_id``, in canonical order, plus the total count."""
    rows = tuple(
        PlaceVerseRef(r[0], r[1], r[2], r[3])
        for r in conn.execute(
            "SELECT pv.book_id, b.name, pv.chapter, pv.verse "
            "FROM place_verses pv JOIN books b ON b.id = pv.book_id "
            "WHERE pv.place_id = ? "
            "ORDER BY b.canonical_order, pv.chapter, pv.verse "
            "LIMIT ? OFFSET ?",
            (place_id, limit, offset),
        )
    )
    total = count_place_verses(conn, place_id)
    return rows, total


def get_places_for_reference(conn: sqlite3.Connection, reference: Reference) -> PlacePage:
    """The distinct places mentioned anywhere in ``reference`` (the union across its spans).

    The inverse of ``get_place_verses``. ``SELECT DISTINCT`` dedups a place named in several
    verses of the range; ordered ``name, id``. No pagination (a reference spans few places).
    """
    clauses: list[str] = []
    params: list[str | int] = [reference.book_id]
    for span in reference.spans:
        predicate, span_params = _span_predicate(span, "pv.chapter", "pv.verse")
        clauses.append(f"({predicate})")
        params += span_params
    where = f"pv.book_id = ? AND ({' OR '.join(clauses)})"

    cols = ", ".join(f"p.{c}" for c in _PLACE_COLS)
    rows = tuple(
        _row_to_place(r)
        for r in conn.execute(
            f"SELECT DISTINCT {cols} "
            "FROM places p JOIN place_verses pv ON pv.place_id = p.id "
            f"WHERE {where} ORDER BY p.name, p.id",
            params,
        )
    )
    return PlacePage(rows=rows, total=len(rows))


def distinct_place_types(conn: sqlite3.Connection) -> list[str]:
    """The set of place ``type`` values present, sorted — for validating a ``?type=`` filter."""
    return [r[0] for r in conn.execute("SELECT DISTINCT type FROM places ORDER BY type")]


# --- topical Bible (mirrors the places queries) --------------------------------------


@dataclass(frozen=True)
class TopicRow:
    """One topic. ``see_also`` is the id of another topic for a 'See X' redirect, else None."""

    id: str
    name: str
    section: str
    see_also: str | None


@dataclass(frozen=True)
class TopicPage:
    """A page of topics plus the total match count."""

    rows: tuple[TopicRow, ...]
    total: int


@dataclass(frozen=True)
class TopicVerseRef:
    """One verse curated under a topic (book id + name for reference formatting)."""

    book_id: str
    book_name: str
    chapter: int
    verse: int


_TOPIC_COLS = ("id", "name", "section", "see_also")
_TOPIC_SELECT = ", ".join(_TOPIC_COLS)


def _row_to_topic(r: sqlite3.Row) -> TopicRow:
    return TopicRow(r[0], r[1], r[2], r[3])


def list_topics(
    conn: sqlite3.Connection,
    q: str | None,
    section: str | None,
    limit: int,
    offset: int,
) -> TopicPage:
    """Browse topics, optionally filtered by name substring (``q``) and ``section`` letter.

    Ordered ``name, id`` (a stable tiebreak so same-named topics paginate deterministically);
    ``total`` is a separate count over the same filter.
    """
    clauses: list[str] = []
    params: list[str] = []
    if q is not None and q.strip():
        clauses.append("name LIKE '%' || ? || '%'")  # case-insensitive for ASCII names
        params.append(q.strip())
    if section is not None and section.strip():
        clauses.append("section = ?")
        params.append(section.strip())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = tuple(
        _row_to_topic(r)
        for r in conn.execute(
            f"SELECT {_TOPIC_SELECT} FROM topics{where} ORDER BY name, id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
    )
    total = conn.execute(f"SELECT COUNT(*) FROM topics{where}", params).fetchone()[0]
    return TopicPage(rows=rows, total=total)


def get_topic(conn: sqlite3.Connection, topic_id: str) -> TopicRow | None:
    """One topic by its stable id, or ``None`` if no such topic."""
    row = conn.execute(f"SELECT {_TOPIC_SELECT} FROM topics WHERE id = ?", (topic_id,)).fetchone()
    return None if row is None else _row_to_topic(row)


def count_topic_verses(conn: sqlite3.Connection, topic_id: str) -> int:
    """How many verses are curated under this topic."""
    return conn.execute(
        "SELECT COUNT(*) FROM topic_verses WHERE topic_id = ?", (topic_id,)
    ).fetchone()[0]


def get_topic_verses(
    conn: sqlite3.Connection, topic_id: str, limit: int, offset: int
) -> tuple[tuple[TopicVerseRef, ...], int]:
    """The verses curated under ``topic_id``, in canonical order, plus the total count."""
    rows = tuple(
        TopicVerseRef(r[0], r[1], r[2], r[3])
        for r in conn.execute(
            "SELECT tv.book_id, b.name, tv.chapter, tv.verse "
            "FROM topic_verses tv JOIN books b ON b.id = tv.book_id "
            "WHERE tv.topic_id = ? "
            "ORDER BY b.canonical_order, tv.chapter, tv.verse "
            "LIMIT ? OFFSET ?",
            (topic_id, limit, offset),
        )
    )
    total = count_topic_verses(conn, topic_id)
    return rows, total


def get_topics_for_reference(conn: sqlite3.Connection, reference: Reference) -> TopicPage:
    """The distinct topics that cite any verse in ``reference`` (the union across its spans).

    The inverse of ``get_topic_verses``. ``SELECT DISTINCT`` dedups a topic that cites several
    verses of the range; ordered ``name, id``. No pagination (a reference cites few topics).
    """
    clauses: list[str] = []
    params: list[str | int] = [reference.book_id]
    for span in reference.spans:
        predicate, span_params = _span_predicate(span, "tv.chapter", "tv.verse")
        clauses.append(f"({predicate})")
        params += span_params
    where = f"tv.book_id = ? AND ({' OR '.join(clauses)})"

    cols = ", ".join(f"t.{c}" for c in _TOPIC_COLS)
    rows = tuple(
        _row_to_topic(r)
        for r in conn.execute(
            f"SELECT DISTINCT {cols} "
            "FROM topics t JOIN topic_verses tv ON tv.topic_id = t.id "
            f"WHERE {where} ORDER BY t.name, t.id",
            params,
        )
    )
    return TopicPage(rows=rows, total=len(rows))


# --- Strong's lexicon (mirrors the topical-Bible queries) ----------------------------


@dataclass(frozen=True)
class StrongsRow:
    """One lexicon entry in summary form (no full definition) — the browse/list shape."""

    strongs_id: str
    language: str
    lemma: str
    transliteration: str
    gloss: str


@dataclass(frozen=True)
class StrongsPage:
    """A page of lexicon entries plus the total match count."""

    rows: tuple[StrongsRow, ...]
    total: int


@dataclass(frozen=True)
class StrongsEntry:
    """One lexicon entry in full — adds the definition and source for the detail view."""

    strongs_id: str
    language: str
    lemma: str
    transliteration: str
    gloss: str
    definition: str
    source: str


_STRONGS_SUMMARY_COLS = ("strongs_id", "language", "lemma", "transliteration", "gloss")
_STRONGS_SUMMARY_SELECT = ", ".join(_STRONGS_SUMMARY_COLS)
# Strong's ids sort numerically within a language (G1, G2, … G26), not lexically (G1, G10, G100).
_STRONGS_ORDER = "language, CAST(SUBSTR(strongs_id, 2) AS INTEGER), strongs_id"


def _row_to_strongs(r: sqlite3.Row) -> StrongsRow:
    return StrongsRow(r[0], r[1], r[2], r[3], r[4])


def list_strongs(
    conn: sqlite3.Connection,
    q: str | None,
    language: str | None,
    limit: int,
    offset: int,
) -> StrongsPage:
    """Browse the lexicon, optionally filtered by ``q`` (substring of lemma, transliteration or
    gloss) and ``language``.

    Ordered by Strong's number within language; ``total`` is a separate count over the same filter.
    """
    clauses: list[str] = []
    params: list[str] = []
    if q is not None and q.strip():
        clauses.append(
            "(lemma LIKE '%' || ? || '%' "
            "OR transliteration LIKE '%' || ? || '%' "
            "OR gloss LIKE '%' || ? || '%')"
        )
        needle = q.strip()
        params += [needle, needle, needle]
    if language is not None and language.strip():
        clauses.append("language = ?")
        params.append(language.strip())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = tuple(
        _row_to_strongs(r)
        for r in conn.execute(
            f"SELECT {_STRONGS_SUMMARY_SELECT} FROM strongs_entries{where} "
            f"ORDER BY {_STRONGS_ORDER} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
    )
    total = conn.execute(f"SELECT COUNT(*) FROM strongs_entries{where}", params).fetchone()[0]
    return StrongsPage(rows=rows, total=total)


def get_strongs(conn: sqlite3.Connection, strongs_id: str) -> StrongsEntry | None:
    """One lexicon entry (with full definition) by its Strong's id, or ``None`` if absent."""
    row = conn.execute(
        "SELECT strongs_id, language, lemma, transliteration, gloss, definition, source "
        "FROM strongs_entries WHERE strongs_id = ?",
        (strongs_id,),
    ).fetchone()
    return None if row is None else StrongsEntry(*row)
