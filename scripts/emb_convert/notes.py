"""EMB's textual and study notes, end to end (V8-S2b, docs/v8/SPEC.md §4.2, ADR-0011).

``build_notes`` runs after the Bible-text pass. It parses both note regions, pairs each
textual note with its ``*`` (``textual.py``), anchors each study note where the book calls it
out (``study.py``), assembles every note's text — Markdown when it needs it (``notetext.py``) —
checks it all, and returns the ``data/private/notes/EMB.json`` payload with what the summary
reports. ``cross_check_epub_notes`` compares the note text with the EPUB's. Nothing here holds
note text: it comes from the operator's PDF at run time.
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from emb_convert import charts, perspectives, topics
from emb_convert.articles import (
    Article,
    ArticleRegion,
    anchors,
    cross_references,
    parse_articles,
    sections,
)
from emb_convert.articles import assign_callouts as assign_article_callouts
from emb_convert.articles import shape as article_shape
from emb_convert.articletext import segment, structures, superscript_markers, write
from emb_convert.clean import CompoundRepair, Fixes, PublicWords, Vocabulary, letters
from emb_convert.crosscheck import CrossCheck, cross_check_notes
from emb_convert.epub_articles import parse_epub_articles, parse_epub_boxes, parse_epub_topics
from emb_convert.epub_notes import EpubNotes, parse_epub_notes
from emb_convert.layout import Layout, canonical_books
from emb_convert.lines import Line, group_lines
from emb_convert.notetext import (
    NoteText,
    Piece,
    assemble,
    emphasis_ok,
    plain_of,
    plain_text,
    relink,
    render,
    run_texts,
)
from emb_convert.pdfxml import PdfDocument, TextItem
from emb_convert.perspectives import Box, BoxRegion
from emb_convert.quotes import QuoteClass, classify
from emb_convert.study import (
    Callouts,
    LinkRun,
    Part,
    RunRefs,
    StudyNote,
    StudyRegion,
    assign_callouts,
    exists,
    link_runs,
    parse_study,
    passages,
    resolve_run,
    separators,
    shape,
    target_verses,
)
from emb_convert.study import separators as run_separators
from emb_convert.text import ParseResult, trusted_text
from emb_convert.textual import (
    LabelKind,
    Matching,
    TextualNote,
    TextualRegion,
    anchor,
    match,
    parse_textual,
)
from emb_convert.topics import Topic, TopicRegion
from emb_convert.validate import PUNCTUATION

TN_LABEL = "Textual Note"
SN_LABEL = "Study Note"
MARKER = "*"
MARKDOWN = "markdown"

Key = tuple[str, int, int]

# Bare references where the book's own link names another book than the text's rule (a bare
# reference belongs to the book before it in a ;/, list, else to the note's book). Each read in
# its sentence and confirmed to mean the note's own book (docs/dev-notes.md, V8-S2b): the note's
# heading and the link as printed — references only.
REVIEWED_LINKS: frozenset[tuple[str, str]] = frozenset(
    {
        ("Judg. 17:1-6", "chapters 17–21"),  # the book links Exodus
        ("Acts 2:14-21", "2:21"),  # Joel
        ("Heb. 1:4-6", "2:11"),  # Psalms
        ("Heb. 6:13-20", "11:8-19"),  # Genesis
        ("Heb. 7:1-3", "6:20"),  # Genesis
        ("Heb. 11:5-7", "11:5"),  # 2 Kings
        ("Heb. 11:5-7", "11:6"),  # Genesis
    }
)

# The articles' bare references read in their sentence (V8-S3a; docs/dev-notes.md): the book
# linked these two to the last book named, but each means the article's own book.
REVIEWED_ARTICLE_LINKS: frozenset[tuple[str, str]] = frozenset(
    {
        ("SYSK 2 Kings 2:9-10", "4:2-7"),  # the book links John
        ("SYSK Daniel 1:6-21", "12:13"),  # the book links Matthew
    }
)
# Spacing the rendered page prints, each checked by eye (docs/dev-notes.md, V8-S3a): an opening
# quote set off from its first word. References only.
ARTICLES_AS_PRINTED: frozenset[tuple[str, str]] = frozenset(
    (name, "space-after-opening-mark")
    for name in (
        "MWG Genesis 1:27 and 2:15-25",
        "SYSK Genesis 6:9–9:29",
        "SYSK Exodus 2:1–4:28",
        "SYSK Judges 13:1–16:31",
        "SYSK 2 Chronicles 29:1–32:33",
    )
)
# ... and this one names its book a sentence earlier, as the book's own link has it.
ARTICLE_LINK_BOOKS: dict[tuple[str, str], str] = {("SYSK Psalms 73:1–83:18", "16:5"): "1CH"}

# Notes where the PDF prints words the EPUB lacks, each checked on the rendered PDF page
# (docs/dev-notes.md, V8-S2b) — the notes' VERIFIED_ON_PAGE. References only.
VERIFIED_NOTES: frozenset[Key] = frozenset(
    {
        ("tn EXO 40:2b", 40, 1),  # a word the EPUB lost
        ("tn ISA 10:22-23", 10, 1),  # a quoted reading, its lines not split by "/"
        ("tn ISA 11:10b", 11, 1),  # the same
        ("tn ISA 28:16b", 28, 1),  # the same
        ("sn 1SA 3:1-10", 0, 1),  # a period the EPUB adds after a reference
        ("sn LUK 12:32-34", 0, 1),  # a word the EPUB lost
    }
)

HYGIENE: dict[str, re.Pattern[str]] = {
    "markup": re.compile(r"[<>]|&\w+;|href|calibre|filepos"),
    "asterisk": re.compile(r"\*"),
    "double-space": re.compile(r"  "),
    "letter-spacing": re.compile(r"(?:^|\s)(?:[A-Za-z] ){2,}[A-Za-z](?:\s|[.,;:!?]|$)"),
    # digits glued to letters — but not ordinals ("430th", small capitals "12TH"), Dead Sea
    # Scrolls sigla ("4QSam",
    # "1QpHab"), a reference to part of a verse ("see 13:2a"), decades ("1960s") or a verse
    # "and following" ("2:15ff")
    "digit-in-word": re.compile(
        r"(?<!\dQ)[A-Za-z]\d|\d(?!(?:st|nd|rd|th|ST|ND|RD|TH|ff)\b|Q[A-Za-z]|[a-e]\b|(?<=0)s\b)[A-Za-z]"
    ),
    "small-caps-fragment": re.compile(r"\bORD\b"),
    **PUNCTUATION,
}


@dataclass(slots=True)
class LinkFinding:
    note: str  # the study note's heading
    link: str  # the link as printed
    targets: list[str]
    evidence: str  # agrees · named · own verse · earlier link · reviewed · no target · unexplained


@dataclass(slots=True)
class ArticleFindings:
    """The feature articles (V8-S3a): what was found, where it went, and its checks."""

    region: ArticleRegion = field(default_factory=ArticleRegion)
    notes: Counter[str] = field(default_factory=Counter[str])  # by feature
    shapes: dict[str, Counter[str]] = field(default_factory=dict[str, Counter[str]])
    structures: dict[str, Counter[str]] = field(default_factory=dict[str, Counter[str]])
    anchors: Counter[tuple[str, str]] = field(default_factory=Counter[tuple[str, str]])
    outside: list[str] = field(default_factory=list[str])
    mid_verse: list[str] = field(default_factory=list[str])
    two_books: list[str] = field(default_factory=list[str])
    words: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    links: list[LinkFinding] = field(default_factory=list[LinkFinding])
    fixes: Counter[str] = field(default_factory=Counter[str])
    gaps_closed: int = 0
    footnotes: int = 0
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])
    order: list[tuple[Key, Article]] = field(default_factory=list[tuple[Key, Article]])
    texts: dict[Key, str] = field(default_factory=dict[Key, str])
    raw: dict[Key, str] = field(default_factory=dict[Key, str])
    solo: dict[str, dict[Key, str]] = field(default_factory=dict[str, dict[Key, str]])
    spans: dict[Key, tuple[int, int]] = field(default_factory=dict[Key, tuple[int, int]])

    @property
    def ok(self) -> bool:
        region = self.region
        return (
            not self.errors
            and not region.unmatched_callouts
            and not region.unindexed
            and not any(self.hygiene.values())
            and all(f.evidence != "unexplained" for f in self.links)
        )


@dataclass(slots=True)
class ChartFindings:
    """EMB's charts (V8-S4b): found, placed and checked."""

    region: charts.ChartRegion = field(default_factory=charts.ChartRegion)
    notes: int = 0
    shapes: Counter[str] = field(default_factory=Counter[str])
    whole_chapters: int = 0  # ranges printed in full that are the whole chapter
    places: Counter[str] = field(default_factory=Counter[str])
    away: list[str] = field(default_factory=list[str])  # inside or after the passage
    passages: int = 0  # notes carrying passages
    mid_verse: list[str] = field(default_factory=list[str])
    link_books: list[str] = field(default_factory=list[str])  # index links into another book
    unused: list[str] = field(default_factory=list[str])  # images no note names once
    spots: dict[int, tuple[str, int, int]] = field(default_factory=dict[int, tuple[str, int, int]])
    assets: dict[str, bytes] = field(default_factory=dict[str, bytes])
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and not self.region.errors
            and not self.region.unclaimed
            and not self.mid_verse
            and not self.link_books
            and not self.unused
            and not any(self.hygiene.values())
        )


@dataclass(slots=True)
class NotesResult:
    payload: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    textual: TextualRegion = field(default_factory=TextualRegion)
    matching: Matching = field(default_factory=Matching)
    study: StudyRegion = field(default_factory=StudyRegion)
    callouts: Callouts = field(default_factory=Callouts)
    label_kinds: Counter[LabelKind] = field(default_factory=Counter[LabelKind])
    anchors: Counter[str] = field(default_factory=Counter[str])
    lettered: tuple[int, int] = (0, 0)  # labels, verses
    shapes: Counter[str] = field(default_factory=Counter[str])
    later_callouts: list[str] = field(default_factory=list[str])
    links: list[LinkFinding] = field(default_factory=list[LinkFinding])
    formats: Counter[tuple[str, str]] = field(default_factory=Counter[tuple[str, str]])
    escapes: int = 0
    fixes: Counter[str] = field(default_factory=Counter[str])
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])
    # for the EPUB cross-check: each note's plain text (fixed, raw, one fix alone) and pages
    texts: dict[Key, str] = field(default_factory=dict[Key, str])
    raw: dict[Key, str] = field(default_factory=dict[Key, str])
    solo: dict[str, dict[Key, str]] = field(default_factory=dict[str, dict[Key, str]])
    spans: dict[Key, tuple[int, int]] = field(default_factory=dict[Key, tuple[int, int]])
    first_study: tuple[str, str] = ("", "")
    articles: ArticleFindings = field(default_factory=ArticleFindings)
    features: FeatureFindings = field(default_factory=lambda: FeatureFindings())
    charts: ChartFindings = field(default_factory=ChartFindings)
    # payload index → (rank, callout order): where an article sorts among notes at its spot
    ranks: dict[int, tuple[int, int]] = field(default_factory=dict[int, tuple[int, int]])
    # payload index → tier: 0 a verse's notes, 1 S3a's articles, 2 S3b's, 3 S4b's charts (each
    # after the last)
    tiers: dict[int, int] = field(default_factory=dict[int, int])
    # id(note) → (tier, reading order): for placing S3b's notes among S3a's at one spot
    reading: dict[int, tuple[int, int]] = field(default_factory=dict[int, tuple[int, int]])

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and self.matching.ok
            and not self.callouts.unmatched
            and not any(self.hygiene.values())
            and all(f.evidence != "unexplained" for f in self.links)
            and self.articles.ok
            and self.features.ok
            and self.charts.ok
        )


def tn_key(note: TextualNote, occurrence: int) -> Key:
    return (f"tn {note.book} {note.label.text}", note.chapter, occurrence)


def sn_key(note: StudyNote, occurrence: int) -> Key:
    return (f"sn {note.book} {note.reference}", 0, occurrence)


@dataclass(slots=True)
class Context:
    """What every note's text is built from."""

    vocabulary: Vocabulary
    repair: CompoundRepair
    verse_text: dict[Key, str]
    verse_pages: dict[Key, tuple[int, int]]
    stored: dict[Key, int]  # a verse absorbed by a combined entry → the entry's stored number
    combined: dict[Key, int]  # a combined entry's stored number → its last number
    last_verse: dict[tuple[str, int], int]
    skeleton: dict[tuple[str, int], int]
    by_alias: dict[str, str]
    names: dict[str, str]
    layout: Layout

    def page_book(self, page: int | None) -> str | None:
        """The book a link's target page sits in."""
        found = self.layout.book_at(page) if page is not None else None
        return found.code if found is not None else None


def context(
    doc: PdfDocument,
    layout: Layout,
    result: ParseResult,
    public: PublicWords,
    skeleton: dict[tuple[str, int], int],
) -> Context:
    seeds = canonical_books()
    bible = group_lines([i for i in doc.items if layout.bible_start <= i.page < layout.notes_start])
    note_lines = group_lines([i for i in doc.items if i.page >= layout.notes_start])
    verse_text: dict[Key, str] = {}
    verse_pages: dict[Key, tuple[int, int]] = {}
    stored: dict[Key, int] = {}
    combined: dict[Key, int] = {}
    last_verse: dict[tuple[str, int], int] = {}
    for book in result.books:
        for chapter in book.chapters:
            last_verse[(book.code, chapter.number)] = max(v.last for v in chapter.verses)
            for verse in chapter.verses:
                key = (book.code, chapter.number, verse.number)
                verse_text[key] = verse.text
                verse_pages[key] = verse.pages
                if verse.last != verse.number:
                    combined[key] = verse.last
                for n in range(verse.number, verse.last + 1):
                    stored[(book.code, chapter.number, n)] = verse.number
    return Context(
        vocabulary=Vocabulary(
            public,
            [*verse_text.values(), *(t for line in note_lines for t in trusted_text(line))],
        ),
        repair=CompoundRepair(line.text for line in bible),
        verse_text=verse_text,
        verse_pages=verse_pages,
        stored=stored,
        combined=combined,
        last_verse=last_verse,
        skeleton=skeleton,
        by_alias={alias: seed.id for seed in seeds for alias in seed.aliases},
        names={seed.id: seed.name for seed in seeds},
        layout=layout,
    )


def _texts(
    result: NotesResult,
    key: Key,
    lines: list[Line],
    ctx: Context,
    *,
    skip: frozenset[int] = frozenset(),
) -> None:
    """Record a note's plain text with no fixes and with each fix alone (the cross-check)."""
    none = Fixes.none()
    scratch: Counter[str] = Counter()

    def plain(fixes: Fixes) -> str:
        return plain_text(
            assemble(lines, ctx.vocabulary, fixes, scratch, repair=ctx.repair, skip=skip)
        )

    result.raw[key] = plain(none)
    for fix in dataclasses.fields(Fixes):
        result.solo.setdefault(fix.name, {})[key] = plain(
            dataclasses.replace(none, **{fix.name: True})
        )
    pages = [line.page for line in lines]
    result.spans[key] = (min(pages), max(pages)) if pages else (0, 0)


def _check_text(result: NotesResult, where: str, text: NoteText) -> None:
    for name, pattern in HYGIENE.items():
        if pattern.search(text.plain):
            result.hygiene.setdefault(name, []).append(where)
    if text.markdown is not None:
        if not emphasis_ok(text.markdown):
            result.hygiene.setdefault("emphasis-flanking", []).append(where)
        if plain_of(text.markdown) != text.plain:
            result.hygiene.setdefault("markdown-round-trip", []).append(where)


_GAPS = re.compile(r"( +)")
_INITIAL = re.compile(r"[A-Z]\.")


def broken_words(pieces: list[Piece], vocabulary: Vocabulary) -> bool:
    """Two tokens the PDF prints a single space apart that join into a word one of them isn't
    ("mak e", "k now"). ``pieces``: the note's text with the PDF's spacing kept — a double
    space is a real word gap ("Abba  ru")."""
    parts = _GAPS.split(plain_text(pieces))
    return any(
        parts[n] == " "
        and not parts[n - 1].endswith(("’", "'"))  # "Name’ s": as the book prints it
        and not _INITIAL.fullmatch(parts[n - 1])  # "Q. Z. Name": initials, not a broken word
        and not (len(b := parts[n + 1].strip(".,;:!?)”’")) > 1 and b.isupper())  # an acronym
        and (a := letters(parts[n - 1]))
        and (b := letters(parts[n + 1]))
        and vocabulary.broken([a, b])
        for n in range(1, len(parts) - 1, 2)
    )


def spaced(lines: list[Line], ctx: Context, skip: frozenset[int] = frozenset()) -> list[Piece]:
    scratch: Counter[str] = Counter()
    return assemble(
        lines, ctx.vocabulary, Fixes(), scratch, repair=ctx.repair, skip=skip, keep_spaces=True
    )


def _note(
    book: str,
    chapter: int,
    verse: int,
    kind: str,
    label: str,
    text: NoteText,
    char_offset: int,
    *,
    marker: str | None = None,
    parts: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    note: dict[str, Any] = {"book": book, "chapter": chapter, "verse": verse, "type": kind}
    note["label"] = label
    note["text"] = text.markdown if text.markdown is not None else text.plain
    if text.markdown is not None:
        note["text_format"] = MARKDOWN
    note["char_offset"] = char_offset
    if marker is not None:
        note["marker"] = marker
    if parts:
        note["passages"] = parts
    return note


# --- textual notes -------------------------------------------------------------------------


def _textual(
    result: NotesResult, doc: PdfDocument, layout: Layout, parse: ParseResult, ctx: Context
) -> None:
    result.textual = parse_textual(doc, layout, ctx.by_alias)
    result.errors += result.textual.errors
    notes = result.textual.notes
    result.label_kinds = Counter(n.label.kind for n in notes)
    lettered = [n for n in notes if n.label.letter]
    result.lettered = (
        len(lettered),
        len({(n.book, n.chapter, n.label.lettered_verse) for n in lettered}),
    )
    result.matching = match(notes, parse.markers, ctx.combined)
    seen: Counter[tuple[str, int, str]] = Counter()
    for pair in result.matching.pairs:
        note = pair.note
        where = note.ref
        place = anchor(pair, ctx.verse_text)
        if isinstance(place, str):
            result.errors.append(place)
            continue
        result.anchors[place.where] += 1
        lines = note.lines
        text = render(
            assemble(
                lines, ctx.vocabulary, Fixes(), result.fixes, repair=ctx.repair, skip=note.label_ids
            )
        )
        _check_text(result, where, text)
        if broken_words(spaced(lines, ctx, note.label_ids), ctx.vocabulary):
            result.hygiene.setdefault("broken-word", []).append(where)
        result.formats[("tn", MARKDOWN if text.markdown else "plain")] += 1
        result.escapes += _escapes(text)
        result.payload.append(
            _note(
                note.book,
                note.chapter,
                place.verse,
                "tn",
                TN_LABEL,
                text,
                place.char_offset,
                marker=MARKER,
            )
        )
        seen[(note.book, note.chapter, note.label.text)] += 1
        key = tn_key(note, seen[(note.book, note.chapter, note.label.text)])
        result.texts[key] = text.plain
        _texts(result, key, lines, ctx, skip=note.label_ids)


def _escapes(text: NoteText) -> int:
    if text.markdown is None:
        return 0
    return len(re.findall(r"\\[\\`*_\[\]<~&>#+\-.)]", text.markdown))


# --- study notes ---------------------------------------------------------------------------


def _resolve_links(
    result: NotesResult,
    book: str,
    heading: str,
    pieces: list[Piece],
    runs: list[LinkRun],
    anchor_verse: tuple[int, int],
    ctx: Context,
) -> tuple[list[Piece], list[str]]:
    """Each link run → its ``ref:`` targets (``study.resolve_run``), with the book's own
    target page as evidence. ``book``/``heading``: the note's book and its name in findings."""
    spans = link_spans(result.links, result.errors, book, heading, pieces, runs, anchor_verse, ctx)
    return relink(pieces, spans)


def link_spans(
    links: list[LinkFinding],
    errors: list[str],
    book: str,
    heading: str,
    pieces: list[Piece],
    runs: list[LinkRun],
    anchor_verse: tuple[int, int],
    ctx: Context,
    note_chapter: int | None = None,
    *,
    reviewed: frozenset[tuple[str, str]] = REVIEWED_LINKS,
    books: dict[tuple[str, str], str] | None = None,
    and_continues: bool = False,
) -> dict[int, list[tuple[int, int, str]]]:
    """Each link run's references as (start, end, target) slices of its text.
    ``note_chapter``: the chapter a bare "v. 25" means (``study.resolve_run``); ``reviewed``:
    links read in their sentence whose book's target disagrees; ``books``: a bare reference
    whose sentence names its book elsewhere (heading, link) → book; ``and_continues``: "and"
    continues a list like "," does ("Joshua 2 and 6", the articles)."""
    separators_ = (",", ";", "and") if and_continues else (",", ";")
    texts = run_texts(pieces)
    before = separators(pieces)
    spans: dict[int, list[tuple[int, int, str]]] = {}
    previous: RunRefs | None = None
    earlier: set[int] = set()
    own = ctx.verse_pages.get((book, *anchor_verse), (0, 0))
    own_pages = set(range(own[0] - 1, own[1] + 2))
    for run_index in sorted(texts):
        text = texts[run_index]
        page = runs[run_index].page
        between = before.get(run_index, "").strip()
        continues = (
            (previous.book, previous.chapter, "," if between == "and" else between)
            if previous is not None and between in separators_
            else None
        )
        refs = resolve_run(
            text,
            note_book=(books or {}).get((heading, text), book),
            continues=continues,
            page_book=ctx.page_book(page),
            by_alias=ctx.by_alias,
            names=ctx.names,
            note_chapter=note_chapter,
        )
        if isinstance(refs, str):
            errors.append(f"{heading}: {refs}")
            spans[run_index] = []
            previous = None
            continue
        for part in refs.parts:
            for target_book, chapter, verse in target_verses(part.target):
                if not exists(ctx.skeleton, target_book, chapter, verse):
                    errors.append(f"{heading}: link {text!r} → {part.target} names no verse")
        spans[run_index] = [(p.start, p.end, p.target) for p in refs.parts]
        links.append(
            LinkFinding(
                heading,
                text,
                [p.target for p in refs.parts],
                _evidence(heading, text, refs, page, own_pages, earlier, ctx, reviewed),
            )
        )
        if page is not None:
            earlier.add(page)
        previous = refs
    return spans


def _evidence(
    heading: str,
    text: str,
    refs: RunRefs,
    page: int | None,
    own_pages: set[int],
    earlier: set[int],
    ctx: Context,
    reviewed: frozenset[tuple[str, str]] = REVIEWED_LINKS,
) -> str:
    if page is None:
        return "no target"
    first = refs.parts[0]
    verse = ctx.stored.get((first.book, first.chapter, first.verse), first.verse)
    span = ctx.verse_pages.get((first.book, first.chapter, verse))
    page_book = ctx.page_book(page)
    if span is not None and page_book == first.book and span[0] - 1 <= page <= span[1] + 1:
        return "agrees"
    if refs.named and page_book != first.book:
        return "named"
    if page in own_pages:
        return "own verse"
    if page in earlier:
        return "earlier link"
    if (heading, text) in reviewed:
        return "reviewed"
    return "unexplained"


def _study(
    result: NotesResult, doc: PdfDocument, layout: Layout, parse: ParseResult, ctx: Context
) -> None:
    result.study = parse_study(doc, layout, ctx.by_alias)
    result.errors += result.study.errors
    notes = result.study.notes
    if notes:
        result.first_study = (notes[0].book, notes[0].reference)
    result.callouts = assign_callouts(notes, parse.diagnostics.callouts)
    seen: Counter[tuple[str, str]] = Counter()
    for n, note in enumerate(notes):
        result.shapes[shape(note, ctx.last_verse)] += 1
        for part in note.parts:
            for chapter, verse in (
                (part.start_chapter, part.start_verse),
                (part.end_chapter, part.end_verse),
            ):
                if not exists(ctx.skeleton, note.book, chapter, verse):
                    result.errors.append(f"{note.heading}: names no verse {chapter}:{verse}")
        at = result.callouts.at.get(n, note.first)
        if n in result.callouts.at and at != note.first:
            result.later_callouts.append(f"{note.heading} (called out at {at[0]}:{at[1]})")
        verse = ctx.stored.get((note.book, *at), at[1])
        if (note.book, at[0], verse) not in ctx.verse_text:
            result.errors.append(f"{note.heading}: anchor {at[0]}:{at[1]} has no text")
            continue
        run_of, runs = link_runs(note.lines)
        pieces = assemble(
            note.lines, ctx.vocabulary, Fixes(), result.fixes, repair=ctx.repair, run_of=run_of
        )
        pieces, targets = _resolve_links(result, note.book, note.heading, pieces, runs, at, ctx)
        text = render(pieces, targets)
        _check_text(result, note.heading, text)
        if broken_words(spaced(note.lines, ctx), ctx.vocabulary):
            result.hygiene.setdefault("broken-word", []).append(note.heading)
        result.formats[("sn", MARKDOWN if text.markdown else "plain")] += 1
        result.escapes += _escapes(text)
        parts = [
            {
                "start_chapter": p.start_chapter,
                "start_verse": p.start_verse,
                "end_chapter": p.end_chapter,
                "end_verse": p.end_verse,
            }
            for p in passages(note, at)
        ]
        result.payload.append(_note(note.book, at[0], verse, "sn", SN_LABEL, text, 0, parts=parts))
        seen[(note.book, note.reference)] += 1
        key = sn_key(note, seen[(note.book, note.reference)])
        result.texts[key] = text.plain
        _texts(result, key, note.lines, ctx)


# --- the whole pass ------------------------------------------------------------------------


# --- feature articles (V8-S3a) -------------------------------------------------------------

ARTICLE = "article"
# At its spot an article called out before its verse shows first (the callout line stands
# above the verse), one closing its passage last (the line stands below the verse's text).
# A verse's notes are served by their ``ordinal`` — by default their place among the verse's
# notes in the file — so every article goes after the verse's other notes in the file (their
# numbers don't move) and one that shows first carries ``ordinal`` 0.
RANK_START, RANK_END = -1, 2
FIRST_ORDINAL = 0


def _articles(
    result: NotesResult, doc: PdfDocument, layout: Layout, parse: ParseResult, ctx: Context
) -> None:
    found = result.articles
    region = parse_articles(doc, layout, ctx.by_alias, ctx.last_verse)
    found.region = region
    found.errors += region.errors
    order = {id(c): n for n, c in enumerate(parse.diagnostics.feature_callouts)}
    assign_article_callouts(region, parse.diagnostics.feature_callouts)

    def is_link(item: TextItem) -> bool:
        page = item.link_page
        return page is None or layout.bible_start <= page < layout.notes_start

    def is_note_marker(item: TextItem) -> bool:
        page = item.link_page
        return (
            item.size == MARKER_SIZE
            and item.blue
            and item.stripped.isdigit()
            and page is not None
            and layout.features_start <= page < layout.study_start
        )

    seen: Counter[tuple[str, str]] = Counter()
    for article in region.articles:
        feature = article.feature
        name = f"{feature.key} {article.reference}"
        seen[(feature.key, article.reference)] += 1
        key: Key = (name, 0, seen[(feature.key, article.reference)])
        found.shapes.setdefault(feature.key, Counter())[article_shape(article, ctx.last_verse)] += 1
        for book, part in article.parts:
            for chapter, verse in (
                (part.start_chapter, part.start_verse),
                (part.end_chapter, part.end_verse),
            ):
                if not exists(ctx.skeleton, book, chapter, verse):
                    found.errors.append(f"{name}: names no verse {book} {chapter}:{verse}")
        places = anchors(article, ctx.stored)
        if isinstance(places, str):
            found.errors.append(f"{name}: {places}")
            continue
        lines = article.lines
        found.footnotes += superscript_markers(lines, is_note_marker)
        run_of, runs = link_runs(lines, is_link)
        scratch: Counter[str] = Counter()

        def inline(
            block: Sequence[Line],
            counts: Counter[str] = scratch,
            run_of: dict[int, int] = run_of,
        ) -> list[Piece]:
            return assemble(
                block,
                ctx.vocabulary,
                Fixes(),
                counts,
                repair=ctx.repair,
                run_of=run_of,
                bold=True,
                split_fused=True,
            )

        flat = inline(lines, found.fixes)
        first = places[0]
        chapters = {
            c for p in article.parts_in(first.book) for c in (p.start_chapter, p.end_chapter)
        }
        spans = link_spans(
            found.links,
            found.errors,
            first.book,
            name,
            flat,
            runs,
            (first.chapter, first.verse),
            ctx,
            note_chapter=chapters.pop() if len(chapters) == 1 else None,
            reviewed=REVIEWED_ARTICLE_LINKS,
            books=ARTICLE_LINK_BOOKS,
            and_continues=True,
        )
        built = segment(lines, opening_quote=feature.head != "title")
        found.errors += [f"{name}: {e}" for e in built.errors]
        byline = ""
        if feature.head == "label":
            credit = article.entry.credit if article.entry is not None else []
            byline = " ".join(credit[0].text.split()) if credit else article.byline
        text = write(built, inline, lambda pieces, spans=spans: relink(pieces, spans), byline)
        found.gaps_closed += text.gaps_closed
        for problem in text.problems:
            found.hygiene.setdefault(problem, []).append(name)
        for pattern_name, pattern in HYGIENE.items():
            if pattern.search(text.plain) and (name, pattern_name) not in ARTICLES_AS_PRINTED:
                found.hygiene.setdefault(pattern_name, []).append(name)
        if broken_words(spaced(lines, ctx), ctx.vocabulary):
            found.hygiene.setdefault("broken-word", []).append(name)
        if _WS_ALL.sub("", plain_text(flat)) != text.printed:
            found.errors.append(f"{name}: its blocks don't hold exactly the text it prints")
        counted = structures(built)
        if byline:
            counted["byline"] += 1
        found.structures.setdefault(feature.key, Counter()).update(counted)
        found.words.setdefault(feature.key, []).append(len(text.plain.split()))
        for place in places:
            verse_text = ctx.verse_text.get((place.book, place.chapter, place.verse))
            if verse_text is None:
                found.errors.append(f"{name}: anchor {place.chapter}:{place.verse} has no text")
                continue
            note: dict[str, Any] = {
                "book": place.book,
                "chapter": place.chapter,
                "verse": place.verse,
                "type": ARTICLE,
                "label": feature.label,
                "title": article.title,
                "text": text.markdown,
                "text_format": MARKDOWN,
                "char_offset": len(verse_text) if place.at_end else 0,
            }
            if not place.at_end:
                note["ordinal"] = FIRST_ORDINAL
            parts = _article_passages(article.parts_in(place.book), (place.chapter, place.verse))
            if parts:
                note["passages"] = parts
            others = cross_references(article, place.book, ctx.last_verse)
            if others:
                note["cross_references"] = others
                found.two_books.append(
                    f"{name}: at {place.book} {place.chapter}:{place.verse}, cross-references "
                    + ", ".join(
                        f"{x['book']} {x['chapter']}:{x['verse_start']}-{x['verse_end']}"
                        for x in others
                    )
                )
            callout = place.callout
            reading = order.get(id(callout), len(order)) if callout is not None else len(order)
            result.ranks[len(result.payload)] = (RANK_END if place.at_end else RANK_START, reading)
            result.tiers[len(result.payload)] = 1
            result.reading[id(note)] = (1, 2 * reading + 1)
            result.payload.append(note)
            found.notes[feature.key] += 1
            where = (
                "never called out"
                if callout is None
                else "book introduction"
                if callout.in_intro
                else "end of a verse"
                if place.at_end
                else "start of a verse"
            )
            found.anchors[(feature.key, where)] += 1
            if place.outside:
                found.outside.append(f"{name} (at {place.book} {place.chapter}:{place.verse})")
            if callout is not None and callout.mid_verse:
                found.mid_verse.append(f"{name} (in {place.book} {place.chapter}:{place.verse})")
        found.order.append((key, article))
        found.texts[key] = plain_text(flat).translate(_DIGITS)
        _article_texts(found.raw, found.solo, found.spans, key, lines, ctx)


_WS_ALL = re.compile(r"\s+")
_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
MARKER_SIZE = 7


# --- What the Bible Says About and Perspectives (V8-S3b) --------------------------------------

WBSA, PERSP = "WBSA", "PERSP"
# Quotations whose words differ from the verse text they cite beyond the classes
# (``quotes.classify``), each read in the book and confirmed as its own edit — words left out
# without ". . ." (docs/dev-notes.md, V8-S3b). Keys:
# feature, topic number in the index, the reference as printed — references only.
QUOTES_AS_PRINTED: frozenset[str] = frozenset(
    {
        "WBSA 18 Luke 12:16-21",  # leaves out a clause and its quotation's inner marks
        "WBSA 6 1 Peter 2:5, 9",  # its second part starts inside the verse
    }
)
# Boxes whose index entry prints another passage than the box itself (the box's own print is
# used). References only.
BOX_INDEX_DIFFERS: frozenset[str] = frozenset({"PERSP Ezekiel 11:1-4"})  # the index: 11:1-3
# Links read in their sentence whose book's target disagrees (none expected).
REVIEWED_FEATURE_LINKS: frozenset[tuple[str, str]] = frozenset()
# Topics or boxes where the PDF prints words the EPUB lacks, checked on the rendered page.
VERIFIED_FEATURES: frozenset[Key] = frozenset(
    {
        ("WBSA 43", 0, 1),  # a period the EPUB adds after a reference
    }
)


@dataclass(slots=True)
class FeatureFindings:
    """What the Bible Says About and Perspectives (V8-S3b): found, placed and checked."""

    topics: TopicRegion = field(default_factory=TopicRegion)
    boxes: BoxRegion = field(default_factory=BoxRegion)
    callouts: int = 0  # callout lines into the topics' section
    notes: Counter[str] = field(default_factory=Counter[str])  # by feature
    quoted: int = 0  # references the topics quote
    pointers: int = 0  # references a topic links on to, not quoted
    two_references: int = 0  # reference lines with two references
    classes: dict[str, Counter[str]] = field(default_factory=dict[str, Counter[str]])
    others: list[str] = field(default_factory=list[str])  # reviewed "other" quotations
    unreviewed: list[str] = field(default_factory=list[str])
    anchors: Counter[tuple[str, str]] = field(default_factory=Counter[tuple[str, str]])
    outside: list[str] = field(default_factory=list[str])
    mid_verse: list[str] = field(default_factory=list[str])
    shown_first: list[str] = field(default_factory=list[str])
    shapes: Counter[str] = field(default_factory=Counter[str])
    structures: dict[str, Counter[str]] = field(default_factory=dict[str, Counter[str]])
    words: dict[str, list[int]] = field(default_factory=dict[str, list[int]])
    links: list[LinkFinding] = field(default_factory=list[LinkFinding])
    fixes: Counter[str] = field(default_factory=Counter[str])
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    errors: list[str] = field(default_factory=list[str])
    topic_order: list[tuple[Key, Topic]] = field(default_factory=list[tuple[Key, Topic]])
    box_order: list[tuple[Key, Box]] = field(default_factory=list[tuple[Key, Box]])
    texts: dict[Key, str] = field(default_factory=dict[Key, str])
    raw: dict[Key, str] = field(default_factory=dict[Key, str])
    solo: dict[str, dict[Key, str]] = field(default_factory=dict[str, dict[Key, str]])
    spans: dict[Key, tuple[int, int]] = field(default_factory=dict[Key, tuple[int, int]])

    @property
    def unexplained_index(self) -> list[Box]:
        return [b for b in self.boxes.index_differs if b.name not in BOX_INDEX_DIFFERS]

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and not self.topics.errors
            and not self.boxes.errors
            and not self.topics.unmatched_callouts
            and not self.topics.unindexed
            and not self.boxes.unindexed
            and not self.unexplained_index
            and not self.unreviewed
            and not any(self.hygiene.values())
            and all(f.evidence != "unexplained" for f in self.links)
        )


Cited = tuple[str, int, int, int, int]  # book, first chapter and verse, last chapter and verse


def _target_range(target: str, ctx: Context) -> Cited:
    """A ``ref:`` target as the verses it spans (a chapter target: the whole chapters)."""
    (book, c1, v1), (_, c2, v2) = target_verses(target)
    if "." not in target.partition(".")[2]:
        return book, c1, 1, c2, ctx.last_verse.get((book, c2), 1)
    return book, c1, v1, c2, v2


def _cited_text(cited: Sequence[Cited], ctx: Context) -> str:
    """The verse text a quotation cites, its verses in order, a combined verse once."""
    texts: list[str] = []
    seen: set[Key] = set()
    for book, c1, v1, c2, v2 in cited:
        for chapter in range(c1, c2 + 1):
            first = v1 if chapter == c1 else 1
            last = v2 if chapter == c2 else ctx.last_verse.get((book, chapter), 0)
            for verse in range(first, last + 1):
                stored = ctx.stored.get((book, chapter, verse))
                key = (book, chapter, stored) if stored is not None else None
                if key is None or key in seen or key not in ctx.verse_text:
                    continue
                seen.add(key)
                texts.append(ctx.verse_text[key])
    return " ".join(texts)


def _covers(cited: Sequence[Cited], book: str, chapter: int, verse: int) -> bool:
    return any(
        b == book and (c1, v1) <= (chapter, verse) <= (c2, v2) for b, c1, v1, c2, v2 in cited
    )


def _features(
    result: NotesResult, doc: PdfDocument, layout: Layout, parse: ParseResult, ctx: Context
) -> None:
    found = result.features
    sections_ = sections(doc, layout)
    callouts = parse.diagnostics.feature_callouts
    reading = {id(c): n for n, c in enumerate(callouts)}

    def is_link(item: TextItem) -> bool:
        page = item.link_page
        return page is not None and layout.bible_start <= page < layout.notes_start

    def inline_for(run_of: dict[int, int], counts: Counter[str]) -> topics.Inline:
        def inline(block: Sequence[Line]) -> list[Piece]:
            return assemble(
                block,
                ctx.vocabulary,
                Fixes(),
                counts,
                repair=ctx.repair,
                run_of=run_of,
                bold=True,
                split_fused=True,
                split_sentences=True,
            )

        return inline

    def check(name: str, lines: list[Line], flat: list[Piece], written: topics.Written) -> None:
        for problem in written.problems:
            found.hygiene.setdefault(problem, []).append(name)
        for pattern_name, pattern in HYGIENE.items():
            if pattern.search(written.plain):
                found.hygiene.setdefault(pattern_name, []).append(name)
        if broken_words(spaced(lines, ctx), ctx.vocabulary):
            found.hygiene.setdefault("broken-word", []).append(name)
        if _WS_ALL.sub("", plain_text(flat)) != written.printed:
            found.errors.append(f"{name}: its blocks don't hold exactly the text it prints")

    def quotation(feature: str, name: str, quoted: str, cited: list[Cited]) -> None:
        kind = classify(quoted, _cited_text(cited, ctx))
        found.classes.setdefault(feature, Counter())[kind.value] += 1
        if kind is QuoteClass.OTHER:
            (found.others if name in QUOTES_AS_PRINTED else found.unreviewed).append(name)

    def add(note: dict[str, Any], feature: str, at_end: bool, order: int) -> None:
        n = len(result.payload)
        result.ranks[n] = (RANK_END if at_end else RANK_START, order)
        result.tiers[n] = 2
        result.reading[id(note)] = (2, order)
        result.payload.append(note)
        found.notes[feature] += 1

    # the topics
    region = topics.parse_topics(doc, layout, sections_)
    found.topics = region
    found.callouts = len(topics.assign_callouts(region, callouts))
    for topic in region.topics:
        name = f"{WBSA} {topic.number}"
        key: Key = (name, 0, 1)
        body = topic.body
        run_of, runs = link_runs(body, is_link)
        inline = inline_for(run_of, Counter())
        flat = inline_for(run_of, found.fixes)(body)
        places: list[tuple[str, int, int, bool, int]] = []  # book, chapter, verse, at end, order
        for callout in topic.callouts:
            if callout.after is not None:
                book, (chapter, verse), at_end = callout.book, callout.after, True
            elif callout.before is not None:
                (book, chapter, verse), at_end = callout.before, False
            else:
                found.errors.append(f"{name}: a callout with no verse by it (p{callout.page})")
                continue
            stored = ctx.stored.get((book, chapter, verse), verse)
            places.append((book, chapter, stored, at_end, 2 * reading[id(callout)] + 1))
        first = places[0] if places else None
        spans = link_spans(
            found.links,
            found.errors,
            first[0] if first is not None else "",
            name,
            flat,
            runs,
            (first[1], first[2]) if first is not None else (0, 0),
            ctx,
            reviewed=REVIEWED_FEATURE_LINKS,
        )
        quoted_all: list[Cited] = []
        for q in topic.quotations:
            line_pieces = inline([q.reference])
            between = run_separators(line_pieces)
            line_runs = list(dict.fromkeys(p.run for p in line_pieces if p.run is not None))
            if len(line_runs) > 1:
                found.two_references += 1
            cited: list[Cited] = []
            for k, run in enumerate(line_runs):
                if k and between.get(run, "").strip() not in (";", ","):
                    found.pointers += 1  # the book points on to it; it doesn't quote it
                    continue
                found.quoted += 1
                cited += [_target_range(target, ctx) for _, _, target in spans.get(run, [])]
            quoted_all += cited
            printed = plain_text(line_pieces).strip().removeprefix("(").removesuffix(")")
            quotation(WBSA, f"{name} {printed}", plain_text(inline(q.lines)), cited)
        if not places:  # never called out: the start of its first quoted verse
            if not quoted_all:
                found.errors.append(f"{name}: no callout and no quoted verse")
                continue
            book, chapter, verse, _, _ = quoted_all[0]
            places.append(
                (book, chapter, ctx.stored.get((book, chapter, verse), verse), False, 1 << 30)
            )
        written = topics.write(topic, inline, lambda pieces, spans=spans: relink(pieces, spans))
        check(name, body, flat, written)
        built = found.structures.setdefault(WBSA, Counter())
        built.update(written.counts)
        built["speaker tags"] += sum(
            1 for q in topic.quotations if plain_text(inline(q.lines)).startswith("[")
        )
        built["omissions marked . . ."] += sum(
            1 for q in topic.quotations if ". . ." in plain_text(inline(q.lines))
        )
        found.words.setdefault(WBSA, []).append(len(written.plain.split()))
        for (book, chapter, verse, at_end, order), callout in zip(
            places, [*topic.callouts, None], strict=False
        ):
            verse_text = ctx.verse_text.get((book, chapter, verse))
            if verse_text is None:
                found.errors.append(f"{name}: anchor {book} {chapter}:{verse} has no text")
                continue
            note: dict[str, Any] = {
                "book": book,
                "chapter": chapter,
                "verse": verse,
                "type": ARTICLE,
                "label": topics.LABEL,
                "title": topic.title,
                "text": written.markdown,
                "text_format": MARKDOWN,
                "char_offset": len(verse_text) if at_end else 0,
            }
            if not at_end:
                note["ordinal"] = FIRST_ORDINAL
            add(note, WBSA, at_end, order)
            if callout is None:
                where = "never called out"
            elif _covers(quoted_all, book, chapter, verse):
                where = "end of a verse it quotes"
            elif any(b == book for b, *_ in quoted_all):
                where = "in a book it quotes elsewhere"
            else:
                where = "in a book it doesn't quote"
            found.anchors[(WBSA, where)] += 1
            if callout is not None and (
                callout.before is None or callout.before[:2] != (book, chapter)
            ):
                found.anchors[(WBSA, "at a chapter's end")] += 1
        found.topic_order.append((key, topic))
        found.texts[key] = plain_text(flat).translate(_DIGITS)
        _article_texts(found.raw, found.solo, found.spans, key, body, ctx)

    # the boxes
    boxes = perspectives.parse_boxes(
        parse.diagnostics.boxes, doc, layout, sections_, ctx.by_alias, ctx.last_verse
    )
    found.boxes = boxes
    for box in boxes.boxes:
        name = box.name
        key = (name, 0, 1)
        found.shapes[perspectives.shape(box, ctx.last_verse)] += 1
        for book, part in box.parts:
            for chapter, verse in (
                (part.start_chapter, part.start_verse),
                (part.end_chapter, part.end_verse),
            ):
                if not exists(ctx.skeleton, book, chapter, verse):
                    found.errors.append(f"{name}: names no verse {book} {chapter}:{verse}")
        place = perspectives.anchor(box, ctx.stored)
        if isinstance(place, str):
            found.errors.append(f"{name}: {place}")
            continue
        body = box.body
        run_of, runs = link_runs(body, is_link)
        inline = inline_for(run_of, Counter())
        flat = inline_for(run_of, found.fixes)(body)
        titled = [
            dataclasses.replace(p, text=perspectives.title_case(p.text)) if p.run is not None else p
            for p in flat
        ]
        spans = link_spans(
            found.links,
            found.errors,
            box.book,
            name,
            titled,
            runs,
            (place.chapter, place.verse),
            ctx,
            reviewed=REVIEWED_FEATURE_LINKS,
        )
        cited = [
            (book, p.start_chapter, p.start_verse, p.end_chapter, p.end_verse)
            for book, p in box.parts
        ]
        quotation(PERSP, name, plain_text(inline(box.quote)), cited)
        written = perspectives.write(box, inline, lambda pieces, spans=spans: relink(pieces, spans))
        check(name, body, flat, written)
        built = found.structures.setdefault(PERSP, Counter())
        built.update(written.counts)
        built["attribution lines"] += len(box.attribution)
        found.words.setdefault(PERSP, []).append(len(written.plain.split()))
        verse_text = ctx.verse_text.get((place.book, place.chapter, place.verse))
        if verse_text is None:
            found.errors.append(f"{name}: anchor {place.chapter}:{place.verse} has no text")
            continue
        note = {
            "book": place.book,
            "chapter": place.chapter,
            "verse": place.verse,
            "type": ARTICLE,
            "label": perspectives.LABEL,
            "text": written.markdown,
            "text_format": MARKDOWN,
            "char_offset": len(verse_text) if place.at_end else 0,
        }
        if not place.at_end:
            note["ordinal"] = FIRST_ORDINAL
        parts = _article_passages([p for _, p in box.parts], (place.chapter, place.verse))
        if parts:
            note["passages"] = parts
        add(note, PERSP, place.at_end, 2 * box.record.callouts_before)
        found.anchors[(PERSP, "end of a verse" if place.at_end else "start of a verse")] += 1
        where = f"{name} (at {place.book} {place.chapter}:{place.verse})"
        if place.outside:
            found.outside.append(where)
        if box.record.mid_verse:
            found.mid_verse.append(where)
        found.box_order.append((key, box))
        found.texts[key] = plain_text(flat).translate(_DIGITS)
        _article_texts(found.raw, found.solo, found.spans, key, body, ctx)


def _charts(
    result: NotesResult, parse: ParseResult, ctx: Context, region: charts.ChartRegion
) -> None:
    """Each chart's note, where its image stands, after every earlier note at that verse."""
    found = result.charts
    found.region = region
    at = {(record.page, record.top): record for record in parse.diagnostics.charts}
    for chart in region.charts:
        if chart.image is None or not chart.media_type:
            continue  # the region recorded why
        record = at.get((chart.image.page, chart.image.top))
        if record is None:
            found.errors.append(f"{chart.key}: the text pass never reached p{chart.image.page}")
            continue
        placed = charts.place(chart, record, ctx.by_alias, ctx.last_verse, ctx.stored)
        if isinstance(placed, str):
            found.errors.append(f"{chart.key}: {placed}")
            continue
        where = f"{chart.key} ({placed.book} {placed.chapter}:{placed.verse})"
        if ctx.page_book(chart.reference_page) != placed.book:
            found.link_books.append(f"{where}: the index links p{chart.reference_page}")
        verse_text = ctx.verse_text.get((placed.book, placed.chapter, placed.verse))
        if verse_text is None:
            found.errors.append(f"{where}: no verse text to anchor at")
            continue
        for name, pattern in HYGIENE.items():
            if pattern.search(chart.title):
                found.hygiene.setdefault(name, []).append(chart.key)
        note: dict[str, Any] = {
            "book": placed.book,
            "chapter": placed.chapter,
            "verse": placed.verse,
            "type": charts.NOTE_TYPE,
            "label": charts.LABEL,
            "title": chart.title,
            "text": f"[{chart.reference}](ref:{placed.target})",
            "text_format": MARKDOWN,
            "char_offset": len(verse_text) if placed.at_end else 0,
        }
        if not placed.at_end:
            note["ordinal"] = FIRST_ORDINAL
        passages = _article_passages(placed.parts, (placed.chapter, placed.verse))
        if passages:
            note["passages"] = passages
            found.passages += 1
        note["image"] = chart.name
        n = len(result.payload)
        result.ranks[n] = (RANK_END if placed.at_end else RANK_START, chart.number)
        result.tiers[n] = 3
        result.payload.append(note)
        found.assets[chart.name] = chart.data
        found.notes += 1
        found.shapes[placed.shape] += 1
        found.whole_chapters += placed.whole_chapter
        found.places[placed.where] += 1
        if placed.where != "closes its passage":
            found.away.append(f"{where}: {placed.where}")
        if record.mid_verse:
            found.mid_verse.append(where)
        if record.after is not None:
            found.spots[chart.number] = (record.book, *record.after)
    used = Counter(note["image"] for note in result.payload if note.get("image"))
    found.unused = sorted(
        {name for name in found.assets if used[name] != 1}
        | {name for name in used if name not in found.assets}
    )


def _article_passages(parts: list[Part], anchor_verse: tuple[int, int]) -> list[dict[str, int]]:
    """Every part of the passage in the note's book — none for a single verse the note
    anchors at (S2b's rule)."""
    if len(parts) == 1:
        p = parts[0]
        if (p.start_chapter, p.start_verse) == (p.end_chapter, p.end_verse) == anchor_verse:
            return []
    return [
        {
            "start_chapter": p.start_chapter,
            "start_verse": p.start_verse,
            "end_chapter": p.end_chapter,
            "end_verse": p.end_verse,
        }
        for p in parts
    ]


def _article_texts(
    raw: dict[Key, str],
    solo: dict[str, dict[Key, str]],
    spans: dict[Key, tuple[int, int]],
    key: Key,
    lines: list[Line],
    ctx: Context,
) -> None:
    """An article's plain text with no fixes and with each fix alone (the cross-check)."""
    none = Fixes.none()
    scratch: Counter[str] = Counter()

    def plain(fixes: Fixes) -> str:
        pieces = assemble(
            lines, ctx.vocabulary, fixes, scratch, repair=ctx.repair, split_fused=True
        )
        return plain_text(pieces).translate(_DIGITS)

    raw[key] = plain(none)
    for fix in dataclasses.fields(Fixes):
        solo.setdefault(fix.name, {})[key] = plain(dataclasses.replace(none, **{fix.name: True}))
    pages = [line.page for line in lines]
    spans[key] = (min(pages), max(pages)) if pages else (0, 0)


_TYPE_ORDER = {"sn": 0, "tn": 1}


def build_notes(
    doc: PdfDocument,
    layout: Layout,
    parse: ParseResult,
    public: PublicWords,
    skeleton: dict[tuple[str, int], int],
    chart_region: charts.ChartRegion | None = None,
) -> NotesResult:
    ctx = context(doc, layout, parse, public, skeleton)
    result = NotesResult()
    _textual(result, doc, layout, parse, ctx)
    _study(result, doc, layout, parse, ctx)
    _articles(result, doc, layout, parse, ctx)
    _features(result, doc, layout, parse, ctx)
    if chart_region is not None:
        _charts(result, parse, ctx, chart_region)
    order = {seed.id: seed.canonical_order for seed in canonical_books()}

    def sort_key(pair: tuple[int, dict[str, Any]]) -> tuple[int, ...]:
        n, note = pair
        rank, callout = result.ranks.get(n, (_TYPE_ORDER.get(note["type"], 0), 0))
        return (
            order[note["book"]],
            note["chapter"],
            note["verse"],
            result.tiers.get(n, 0),  # each slice's notes after the verse's earlier ones
            note["char_offset"],
            rank,
            callout,
            n,
        )

    result.payload = [note for _, note in sorted(enumerate(result.payload), key=sort_key)]
    _show_in_print_order(result)
    return result


def _show_in_print_order(result: NotesResult) -> None:
    """An S3b note the book prints above an S3a article at the same verse end takes an
    explicit ``ordinal`` one below the article's, so it shows first. The file keeps it after
    every earlier note at the verse, so no earlier note's number moves (a verse's notes are
    served by ``ordinal``, by default their place among the verse's notes in the file, then
    by file order)."""
    seq: Counter[tuple[str, int, int]] = Counter()
    shown: dict[int, int] = {}
    at: dict[tuple[str, int, int], list[int]] = {}
    for n, note in enumerate(result.payload):
        key = (note["book"], note["chapter"], note["verse"])
        seq[key] += 1
        shown[n] = note.get("ordinal", seq[key])
        at.setdefault(key, []).append(n)
    for indexes in at.values():
        for n in indexes:
            note = result.payload[n]
            tier, reading = result.reading.get(id(note), (0, 0))
            if tier != 2 or not note["char_offset"]:
                continue
            later = [
                shown[m]
                for m in indexes
                if result.reading.get(id(result.payload[m]), (0, 0))[0] == 1
                and result.payload[m]["char_offset"]
                and result.reading[id(result.payload[m])][1] > reading
            ]
            if not later:
                continue
            ordinal = min(later) - 1
            if ordinal < 0:
                result.features.errors.append(f"no ordinal shows a note before its article: {n}")
                continue
            placed: dict[str, Any] = {}
            for name, value in note.items():
                placed[name] = value
                if name == "char_offset":
                    placed["ordinal"] = ordinal
            result.payload[n] = placed
            result.features.shown_first.append(
                f"{note['book']} {note['chapter']}:{note['verse']} (ordinal {ordinal})"
            )


def notes_payload(result: NotesResult, code: str) -> dict[str, Any]:
    return {"translation": code, "notes": result.payload}


def cross_check_epub_notes(
    result: NotesResult,
    epub_path: Path,
    doc: PdfDocument,
    layout: Layout,
    verse_texts: dict[Key, str],
) -> CrossCheck:
    """The note text, PDF vs EPUB, keyed by note (V8-S2b)."""
    seeds = canonical_books()
    by_alias = {alias: seed.id for seed in seeds for alias in seed.aliases}
    books = list(dict.fromkeys(note.book for note in result.textual.notes))
    epub = parse_epub_notes(epub_path, by_alias, result.first_study, books)
    texts, damaged = _epub_keys(epub, set(result.texts))
    pages: dict[int, list[str]] = {}
    for item in doc.items:
        if item.page >= layout.notes_start:
            pages.setdefault(item.page, []).append(item.text)
    return cross_check_notes(
        fixed=result.texts,
        raw=result.raw,
        solo=result.solo,
        epub=texts,
        epub_damaged=damaged,
        context_texts={**verse_texts, **result.texts},
        pages={page: " ".join(t) for page, t in pages.items()},
        spans=result.spans,
        verified=VERIFIED_NOTES,
    )


def _epub_keys(epub: EpubNotes, pdf: set[Key]) -> tuple[dict[Key, str], set[Key]]:
    """The EPUB's notes under the PDF's keys. A study heading the EPUB cut short ("Rev. 12:1"
    for "12:1-17") takes the one PDF note in its book that it begins, and counts as damaged."""
    texts: dict[Key, str] = {}
    damaged: set[Key] = set()
    for (book, chapter, label, occurrence), text in epub.textual.items():
        key = (f"tn {book} {label}", chapter, occurrence)
        texts[key] = text
        if (book, str(chapter), label, str(occurrence)) in epub.damaged:
            damaged.add(key)
    for (book, reference, occurrence), text in epub.study.items():
        key = (f"sn {book} {reference}", 0, occurrence)
        if key not in pdf:
            prefix = f"sn {book} {reference}-"
            longer = [k for k in pdf if k[0].startswith(prefix) and k[2] == occurrence]
            if len(longer) == 1 and longer[0] not in texts:
                key = longer[0]
                damaged.add(key)
        texts[key] = text
        if (book, reference, str(occurrence)) in epub.damaged:
            damaged.add(key)
    return texts, damaged


def cross_check_epub_articles(
    result: NotesResult,
    epub_path: Path,
    doc: PdfDocument,
    layout: Layout,
    verse_texts: dict[Key, str],
) -> CrossCheck:
    """The article text, PDF vs EPUB, keyed by article (V8-S3a): the printed body, from the
    first line after the heading to the last, against the EPUB's same span."""
    found = result.articles
    epub = parse_epub_articles(epub_path, found.order)
    pages: dict[int, list[str]] = {}
    for item in doc.items:
        if layout.features_start <= item.page < layout.study_start:
            pages.setdefault(item.page, []).append(item.text)
    return cross_check_notes(
        fixed=found.texts,
        raw=found.raw,
        solo=found.solo,
        epub=epub.texts,
        epub_damaged=epub.damaged,
        context_texts={**verse_texts, **result.texts, **found.texts},
        pages={page: " ".join(t) for page, t in pages.items()},
        spans=found.spans,
        verified=VERIFIED_ARTICLES,
    )


# Articles where the PDF prints words the EPUB lacks, each checked on the rendered PDF page:
# the words sit in the article's own text flow (docs/dev-notes.md, V8-S3a). Keys: (feature +
# printed passage, 0, occurrence) — references only.
VERIFIED_ARTICLES: frozenset[Key] = frozenset(
    {
        ("MWG Job 2:9-10", 0, 1),  # a word the EPUB lost
        ("MWG Matthew 1", 0, 1),  # the same
        ("MWG John 19:23-27", 0, 1),  # the same
        ("SYSK 1 Samuel 1:19–3:21", 0, 1),  # a paragraph the EPUB lost
        ("SYSK 1 Kings 17:1–19:21", 0, 1),  # a word of the closing line
        ("SYSK Acts 10:1-48", 0, 1),  # two words the EPUB lost
        ("SYSK 1 Timothy 1:7-8", 0, 1),  # a word the EPUB lost
        ("SYSK 3 John 1:9-10", 0, 1),  # two words the EPUB lost
        ("PG Job 33:14", 0, 1),  # a word the EPUB lost
        ("PG Isaiah 57:18-21", 0, 1),  # a word of the epigraph
    }
)


def cross_check_epub_features(
    result: NotesResult,
    epub_path: Path,
    doc: PdfDocument,
    layout: Layout,
    verse_texts: dict[Key, str],
) -> CrossCheck:
    """The topics' and boxes' text, PDF vs EPUB (V8-S3b): a topic keyed by its number in the
    index, a box by its printed passage."""
    found = result.features
    epub_topics = parse_epub_topics(epub_path, found.topic_order)
    epub_boxes = parse_epub_boxes(epub_path, found.box_order)
    wanted = {page for _, box in found.box_order for page in range(box.page, box.page + 2)}
    section = found.topics.section
    pages: dict[int, list[str]] = {}
    for item in doc.items:
        if item.page in wanted or (section is not None and section.holds(item.page)):
            pages.setdefault(item.page, []).append(item.text)
    return cross_check_notes(
        fixed=found.texts,
        raw=found.raw,
        solo=found.solo,
        epub={**epub_topics.texts, **epub_boxes.texts},
        epub_damaged=epub_topics.damaged | epub_boxes.damaged,
        context_texts={**verse_texts, **result.texts, **result.articles.texts, **found.texts},
        pages={page: " ".join(t) for page, t in pages.items()},
        spans=found.spans,
        verified=VERIFIED_FEATURES,
    )
