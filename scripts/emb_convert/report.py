"""The verification summary every run prints (counts and verse references, never text)."""

from __future__ import annotations

from collections import Counter

from emb_convert.articles import FEATURES
from emb_convert.crosscheck import CrossCheck, Verdict
from emb_convert.notes import NotesResult
from emb_convert.quotes import QuoteClass
from emb_convert.text import ParseResult
from emb_convert.textual import LabelKind
from emb_convert.validate import Validation

# The S1 acceptance targets (docs/v8/SPEC.md §3, as corrected by the S1 parse).
EXPECTED: dict[str, int] = {
    "chapters": 1189,
    "verses": 31064,
    "combined": 24,
    "headings": 2197,
    "labels": 59,
    "markers": 4817,
    "perspectives-boxes": 26,
    "italic:psalm-title": 163,
    "italic:psalm-verse-text": 97,
    "italic:sentence-continuation": 15,
    "italic:stanza-label": 22,
    "italic:speaker-label": 37,
    # V8-S2b (docs/v8/SPEC.md §3, as corrected by the S2b parse)
    "textual-notes": 4817,
    "note-blocks": 1072,
    "study-notes": 2467,
    # V8-S3a (docs/v8/SPEC.md §3, as corrected by the S3a parse: 101 Men, Women, and God)
    "MWG-articles": 101,
    "SYSK-articles": 94,
    "PG-articles": 24,
    "callouts": 269,
    "MWG-callouts": 101,
    "SYSK-callouts": 94,
    "PG-callouts": 24,
    "What the Bible Says About Index-callouts": 50,
    # V8-S3b (docs/v8/SPEC.md §3, as corrected by the S3b parse: 50 topics)
    "WBSA-entries": 50,
    "WBSA-topics": 50,
    "WBSA-quotations": 502,
    "WBSA-quoted": 503,
    "WBSA-subheads": 240,  # 242 lines: two wrap
    "WBSA-callouts": 50,
    "PERSP-boxes": 26,
    "PERSP-entries": 26,
}


def _row(label: str, value: int, key: str | None = None) -> str:
    target = EXPECTED.get(key or "")
    mark = "" if target is None else ("  ✓" if value == target else f"  ≠ target {target:,}")
    return f"  {label:<34}{value:>8,}{mark}"


def summary(
    result: ParseResult,
    validation: Validation,
    cross: CrossCheck | None,
    *,
    source: str,
    pages: int,
    poppler: str,
) -> list[str]:
    diag = result.diagnostics
    counts = diag.counts
    chapters = sum(len(b.chapters) for b in result.books)
    verses = sum(len(c.verses) for b in result.books for c in b.chapters)
    labels = counts["italic:stanza-label"] + counts["italic:speaker-label"]
    lines = [
        f"EMB converter — {source} ({pages:,} pages, pdftohtml {poppler})",
        "",
        "Text",
        _row("chapters", chapters, "chapters"),
        _row("verses", verses, "verses"),
        _row("combined verses (first number kept)", len(diag.combined), "combined"),
        _row("section headings", counts["headings"] - labels, "headings"),
        _row("labels as headings (Ps 119, Song)", labels, "labels"),
        _row("psalm titles (prefixed to verse 1)", counts["psalm-titles"]),
        _row("* markers recorded", len(result.markers), "markers"),
        _row("Perspectives boxes set aside", counts["perspectives-boxes"], "perspectives-boxes"),
        _row("callout label lines set aside", counts["callout-lines"]),
        _row("tables", len(diag.tables)),
        _row("table rows", counts["table-rows"]),
        "",
        "Italic-only lines inside chapters",
        _row("psalm title lines", counts["italic:psalm-title"], "italic:psalm-title"),
        _row(
            "Interlude / refrain (verse text)",
            counts["italic:psalm-verse-text"],
            "italic:psalm-verse-text",
        ),  # fmt: skip
        _row(
            "unfinished sentence (verse text)",
            counts["italic:sentence-continuation"],
            "italic:sentence-continuation",
        ),  # fmt: skip
        _row(
            "Ps 119 stanza labels (headings)", counts["italic:stanza-label"], "italic:stanza-label"
        ),  # fmt: skip
        _row(
            "Song speaker labels (headings)", counts["italic:speaker-label"], "italic:speaker-label"
        ),  # fmt: skip
        _row("unclaimed", counts["italic:unclaimed"]),
        "",
        "PDF quirks fixed",
        _row("broken words joined (items)", counts["letter-spaced"]),
        _row("fractions", counts["fractions"]),
        _row("compound hyphens restored", counts["compound-hyphens"]),
        _row("table cells moved back (page split)", sum(t.split_cells_moved for t in diag.tables)),
        _row("chapter turns by label (11:1)", counts["chapter-labels"]),
        "",
        "Checks (any failure blocks writing EMB.json)",
        f"  verse sequence vs KJV skeleton      {_ok(not validation.sequence)}",
        f"  chapters vs skeleton + nav lists    {_ok(not validation.chapters)}",
        f"  hygiene, punctuation spacing        {_ok(not any(validation.hygiene.values()))}",
        f"  unclassified items                  {_ok(not diag.unclassified)}",
        f"  parse errors                        {_ok(not diag.errors)}",
    ]
    for problem in validation.sequence + validation.chapters + diag.errors:
        lines.append(f"    ✗ {problem}")
    for name, refs in validation.hygiene.items():
        lines.append(f"    ✗ {name}: {len(refs)} — {', '.join(refs[:8])}")
    for where in diag.unclassified[:20]:
        lines.append(f"    ✗ unclassified {where}")
    if diag.mid_verse_headings:
        lines += ["", f"Mid-verse headings (attached before the verse they interrupt): "
                      f"{len(diag.mid_verse_headings)}",
                  "  " + ", ".join(diag.mid_verse_headings)]  # fmt: skip
    lines += ["", "Combined verses: " + ", ".join(diag.combined)]
    if cross is not None:
        lines += ["", *cross_summary(cross)]
    return lines


def _ok(passed: bool) -> str:
    return "✓" if passed else "✗"


def cross_summary(
    cross: CrossCheck,
    title: str = "Cross-check: PDF parse vs EPUB, verse by verse",
    *,
    headings: bool = True,
) -> list[str]:
    fixes = Counter(
        name for f in cross.findings if f.verdict is Verdict.FIXED_QUIRK for name in f.fixes
    )
    open_clean = cross.open_in_clean_verses()
    open_damaged = [f for f in cross.findings if f.verdict is Verdict.OPEN and f.epub_damaged]
    regressions = [f for f in cross.findings if f.verdict is Verdict.FIX_REGRESSION]
    heading_kinds = Counter(h.kind for h in cross.headings)
    lines = [
        title,
        _row("agree", cross.count(Verdict.AGREE)),
        _row("fixed PDF quirk", cross.count(Verdict.FIXED_QUIRK)),
    ]
    lines += [_row(f"  by {name}", n) for name, n in sorted(fixes.items())]
    lines += [
        f"  {'fix regressions':<34}{len(regressions):>8,}  (target 0)",
        _row("EPUB damage, visible", cross.count(Verdict.EPUB_VISIBLE)),
        _row("EPUB splice (words from elsewhere)", cross.count(Verdict.EPUB_SPLICE)),
        _row("EPUB loss, evidence at the spot", cross.count(Verdict.EPUB_LOSS)),
        _row("hyphenation variant (PDF as printed)", cross.count(Verdict.SPELLING)),
        _row("verified on the rendered PDF page", cross.count(Verdict.VERIFIED)),
        f"  {'open, EPUB text without damage':<34}{len(open_clean):>8,}  (target 0)",
        _row("open, EPUB text visibly damaged", len(open_damaged)),
    ]
    for f in regressions + open_clean:
        lines.append(f"    ✗ {f.verdict.value} {' '.join(map(str, f.key))} {f.detail}")
    if open_damaged:
        lines.append("    " + ", ".join(_where(f.key) for f in open_damaged))
    if headings:
        lines += ["", "Headings the two parses don't share"]
        lines += [_row(kind, n) for kind, n in sorted(heading_kinds.items())]
    return lines


def _where(key: tuple[str, int, int]) -> str:
    """A verse ("DAN 9:3") or a note ("tn GEN 1:1", "sn GEN 1:26-27") by reference."""
    first, chapter, number = key
    if first.startswith(("tn ", "sn ")):
        return first[3:] + (f" #{number}" if number > 1 else "")
    if chapter == 0:  # an article: its feature and printed passage
        return first + (f" #{number}" if number > 1 else "")
    return f"{first} {chapter}:{number}"


_LABEL_ORDER = [
    LabelKind.VERSE,
    LabelKind.LETTERED,
    LabelKind.RANGE,
    LabelKind.TITLE,
    LabelKind.CHAPTER,
    LabelKind.SINGLE,
]
_ANCHOR_ORDER = ["verse", "psalm title", "chapter header", "heading"]
_SHAPE_ORDER = ["range", "verse", "whole chapter", "cross-chapter", "multi-part"]
# How a link's own target page (the book's) relates to the reference its text names
_EVIDENCE = [
    ("agrees", "target agrees (±1 page)"),
    ("named", "named book, target elsewhere"),
    ("earlier link", "target repeats an earlier link's"),
    ("own verse", "target is the note's own verse"),
    ("reviewed", "bare reference, read in context"),
    ("no target", "no target in the book"),
    ("unexplained", "unexplained"),
]


def notes_summary(notes: NotesResult, cross: CrossCheck | None) -> list[str]:
    """The V8-S2b section: textual and study notes, their checks and the notes cross-check."""
    matching = notes.matching
    labels, verses = notes.lettered
    targets = sum(len(f.targets) for f in notes.links)
    evidence = Counter(f.evidence for f in notes.links)
    formats = notes.formats
    markdown = formats["tn", "markdown"] + formats["sn", "markdown"]
    plain = formats["tn", "plain"] + formats["sn", "plain"]
    lines = [
        "Notes (notes/EMB.json)",
        _row("textual notes", len(notes.textual.notes), "textual-notes"),
        *(_row(f"  label {kind.value}", notes.label_kinds[kind]) for kind in _LABEL_ORDER),
        *(_row(f"  anchor: {where}", notes.anchors[where]) for where in _ANCHOR_ORDER),
        f"  {'a/b splits (across the labels)':<34}{labels:>8,}  labels in {verses:,} verses",
        _row("chapter blocks", notes.textual.blocks, "note-blocks"),
        _row("* markers matched to a note", len(matching.pairs), "markers"),
        f"  {'markers without a note':<34}{len(matching.markers_without_note):>8,}  (target 0)",
        f"  {'notes without a marker':<34}{len(matching.notes_without_marker):>8,}  (target 0)",
        _row("* links to the next page", len(matching.next_page)),
    ]
    if matching.next_page:
        lines.append("    the note starts at a page's foot: " + ", ".join(matching.next_page))
    lines += [
        _row("study notes", len(notes.study.notes), "study-notes"),
        *(_row(f"  {name}", notes.shapes[name]) for name in _SHAPE_ORDER),
        _row("callouts (blue verse numbers)", len(notes.callouts.at)),
        _row("  at the note's first verse", len(notes.callouts.at) - len(notes.later_callouts)),
        _row("  at a later part (anchored there)", len(notes.later_callouts)),
    ]
    lines += [f"      {where}" for where in notes.later_callouts]
    lines += [
        _row("  notes without their own", len(notes.study.notes) - len(notes.callouts.at)),
        f"  {'  callouts without a note':<34}{len(notes.callouts.unmatched):>8,}  (target 0)",
        f"  {'ref: links':<34}{len(notes.links):>8,}  → {targets:,} targets",
        *(_row(f"  {label}", evidence[key]) for key, label in _EVIDENCE if key != "unexplained"),
        f"  {'  unexplained':<34}{evidence['unexplained']:>8,}  (target 0)",
        f"  {'text: Markdown / plain':<34}{markdown:>8,} / {plain:,}"
        f"  (textual {formats['tn', 'markdown']:,} / {formats['tn', 'plain']:,},"
        f" study {formats['sn', 'markdown']:,} / {formats['sn', 'plain']:,})",
        _row("Markdown escapes", notes.escapes),
        _row("broken words joined (items)", notes.fixes["letter-spaced"]),
        _row("fused compounds repaired", notes.fixes["compound-hyphens"]),
        _row("fractions", notes.fixes["fractions"]),
        "",
        "Notes checks (any failure blocks writing)",
        f"  textual notes ↔ * markers         {_ok(matching.ok)}",
        f"  study-note callouts               {_ok(not notes.callouts.unmatched)}",
        f"  ref: links explained              {_ok(not evidence['unexplained'])}",
        f"  hygiene, flanking, round trip     {_ok(not any(notes.hygiene.values()))}",
        f"  parse errors                      {_ok(not notes.errors)}",
    ]
    problems = [
        *(f"marker without a note: {m.book} {m.chapter}:{m.verse} ({m.where.value})"
          for m in matching.markers_without_note),
        *(f"note without a marker: {n.book} {n.chapter}:{n.label.text}"
          for n in matching.notes_without_marker),
        *matching.letter_errors,
        *matching.page_errors,
        *(f"callout without a note: {c.book} {c.chapter}:{c.verse}"
          for c in notes.callouts.unmatched),
        *(f"unexplained link: {f.note} {f.link!r} → {', '.join(f.targets)}"
          for f in notes.links if f.evidence == "unexplained"),
        *notes.errors,
    ]  # fmt: skip
    lines += [f"    ✗ {problem}" for problem in problems[:40]]
    for name, where in notes.hygiene.items():
        lines.append(f"    ✗ {name}: {len(where)} — {', '.join(where[:8])}")
    if cross is not None:
        lines += [
            "",
            *cross_summary(
                cross, "Cross-check: note text, PDF vs EPUB, note by note", headings=False
            ),
        ]
    return lines


_FEATURE_NAMES = {feature.key: feature.label for feature in FEATURES}
_ARTICLE_SHAPES = [
    "range",
    "whole chapter",
    "whole chapters",
    "cross-chapter",
    "verse",
    "multi-part",
    "two books",
    "whole book",
]
_STRUCTURES = [
    "lead-in capitals",
    "headline",
    "paragraph",
    "subhead",
    "quote",
    "quoted paragraphs",
    "poetry",
    "quoted lines",
    "list",
    "list items",
    "numbered list",
    "numbered items",
    "numbered items with paragraphs",
    "source note",
    "closing line",
    "byline",
]
_ANCHORS = ["end of a verse", "start of a verse", "book introduction", "never called out"]


def articles_summary(notes: NotesResult, cross: CrossCheck | None) -> list[str]:
    """The V8-S3a section: the feature articles, their callouts, anchors, text and checks."""
    found = notes.articles
    region = found.region
    callouts = [c for a in region.articles for c in a.callouts]
    by_feature = Counter(a.feature.key for a in region.articles for _ in a.callouts)
    in_intros = sum(1 for c in callouts if c.in_intro)
    total = len(callouts) + len(region.unmatched_callouts) + sum(region.other_callouts.values())
    evidence = Counter(f.evidence for f in found.links)
    targets = sum(len(f.targets) for f in found.links)
    lines = [
        "Feature articles (notes/EMB.json, type article)",
        _row("callout lines, all features", total, "callouts"),
        _row("  in book introductions", in_intros + sum(
            1 for c in region.unmatched_callouts if c.in_intro
        )),
        *(_row(f"  {_FEATURE_NAMES[k]}", by_feature[k], f"{k}-callouts") for k in _FEATURE_NAMES),
        *(_row(f"  {name.removesuffix(' Index')} (below)", n, f"{name}-callouts")
          for name, n in sorted(region.other_callouts.items())),
        f"  {'callouts without an article':<34}{len(region.unmatched_callouts):>8,}  (target 0)",
    ]  # fmt: skip
    for key, name in _FEATURE_NAMES.items():
        mine = [a for a in region.articles if a.feature.key == key]
        words = sorted(found.words.get(key, [0]))
        shapes = found.shapes.get(key, Counter())
        built = found.structures.get(key, Counter())
        lines += [
            _row(f"{name} articles", len(mine), f"{key}-articles"),
            _row("  index entries", len(region.entries.get(key, []))),
            _row("  called out once", sum(1 for a in mine if len(a.callouts) == 1)),
            _row("  called out more than once", sum(1 for a in mine if len(a.callouts) > 1)),
            _row("  never called out", sum(1 for a in mine if not a.callouts)),
            _row("  notes", found.notes[key]),
            *(_row(f"  anchor: {where}", found.anchors[key, where]) for where in _ANCHORS
              if found.anchors[key, where]),
            *(_row(f"  passage: {shape}", shapes[shape]) for shape in _ARTICLE_SHAPES
              if shapes[shape]),
            *(_row(f"  {what}", built[what]) for what in _STRUCTURES if built[what]),
            f"  {'words: shortest / median / longest':<34}{words[0]:>8,} / "
            f"{words[len(words) // 2]:,} / {words[-1]:,}",
        ]  # fmt: skip
    renamed = [f"{a.feature.key} {a.reference}" for a in region.renamed]
    lines += [
        _row("anchors outside the passage", len(found.outside)),
        *(f"      {where}" for where in found.outside),
        _row("callout lines inside a verse", len(found.mid_verse)),
        *(f"      {where}" for where in found.mid_verse),
        _row("passages in two books", len(found.two_books)),
        *(f"      {where}" for where in found.two_books),
        _row("index names its article otherwise", len(renamed)),
        *(f"      {where} (title from the index)" for where in renamed),
        _row("Personal Gold author notes (V8-S5)", region.authors),
        _row("Personal Gold credits (V8-S5)", sum(
            1 for e in region.entries.get("PG", []) if e.credit
        )),
        f"  {'ref: links':<34}{len(found.links):>8,}  → {targets:,} targets",
        *(_row(f"  {label}", evidence[key]) for key, label in _EVIDENCE if key != "unexplained"),
        f"  {'  unexplained':<34}{evidence['unexplained']:>8,}  (target 0)",
        _row("broken words joined (items)", found.fixes["letter-spaced"]),
        _row("words the italic font ran together", found.fixes["fused-words"]),
        _row("passage font's breaks after m", region.m_breaks),
        _row("opening-mark gaps closed", found.gaps_closed),
        _row("source-note numbers (superscript)", found.footnotes),
        "",
        "Articles checks (any failure blocks writing)",
        f"  every callout matched             {_ok(not region.unmatched_callouts)}",
        f"  every article indexed and placed  {_ok(not region.unindexed)}",
        f"  ref: links explained              {_ok(not evidence['unexplained'])}",
        f"  hygiene, flanking, round trip     {_ok(not any(found.hygiene.values()))}",
        f"  parse errors                      {_ok(not found.errors)}",
    ]  # fmt: skip
    problems = [
        *(f"callout without an article: {c.book} p{c.page}" for c in region.unmatched_callouts),
        *(f"article without its index entry: {a.feature.key} {a.reference}"
          for a in region.unindexed),
        *(f"unexplained link: {f.note} {f.link!r} → {', '.join(f.targets)}"
          for f in found.links if f.evidence == "unexplained"),
        *found.errors,
    ]  # fmt: skip
    lines += [f"    ✗ {problem}" for problem in problems[:40]]
    for name, where in found.hygiene.items():
        lines.append(f"    ✗ {name}: {len(where)} — {', '.join(where[:8])}")
    if cross is not None:
        lines += [
            "",
            *cross_summary(
                cross, "Cross-check: article text, PDF vs EPUB, article by article", headings=False
            ),
        ]
    return lines


_QUOTE_CLASSES = [c.value for c in QuoteClass]
_TOPIC_ANCHORS = [
    "end of a verse it quotes",
    "in a book it quotes elsewhere",
    "in a book it doesn't quote",
    "never called out",
    "at a chapter's end",
]
_BOX_SHAPES = ["range", "verse", "multi-part", "whole chapter", "cross-chapter"]


def _words(counts: list[int]) -> str:
    words = sorted(counts or [0])
    return (
        f"  {'words: shortest / median / longest':<34}{words[0]:>8,} / "
        f"{words[len(words) // 2]:,} / {words[-1]:,}"
    )


def features_summary(notes: NotesResult, cross: CrossCheck | None) -> list[str]:
    """The V8-S3b section: What the Bible Says About and Perspectives."""
    found = notes.features
    region, boxes = found.topics, found.boxes
    evidence = Counter(f.evidence for f in found.links)
    targets = sum(len(f.targets) for f in found.links)
    called = Counter(len(t.callouts) for t in region.topics)
    wbsa_built = found.structures.get("WBSA", Counter[str]())
    persp_built = found.structures.get("PERSP", Counter[str]())
    lines = [
        "Topics and Perspectives (notes/EMB.json, type article)",
        _row("What the Bible Says About index", len(region.entries), "WBSA-entries"),
        _row("  topics", len(region.topics), "WBSA-topics"),
        _row("  quotations", sum(len(t.quotations) for t in region.topics), "WBSA-quotations"),
        _row("  quoted references", found.quoted, "WBSA-quoted"),
        _row("  references linked, not quoted", found.pointers),
        _row("  reference lines with two", found.two_references),
        _row("  callout lines", found.callouts, "WBSA-callouts"),
        _row("  called out once", called[1]),
        _row("  called out more than once", sum(n for k, n in called.items() if k > 1)),
        _row("  never called out", called[0]),
        f"  {'  callouts without a topic':<34}{len(region.unmatched_callouts):>8,}  (target 0)",
        _row("  notes", found.notes["WBSA"]),
        *(_row(f"  anchor: {where}", found.anchors["WBSA", where]) for where in _TOPIC_ANCHORS
          if found.anchors["WBSA", where]),
        _row("  subheads", wbsa_built["subheads"], "WBSA-subheads"),
        *(_row(f"  {what}", n) for what, n in sorted(wbsa_built.items())
          if what not in ("subheads", "quotations")),
        *(_row(f"  quotation: {kind}", found.classes.get("WBSA", Counter())[kind])
          for kind in _QUOTE_CLASSES),
        _words(found.words.get("WBSA", [])),
        _row("  index names its topic otherwise", len(region.renamed)),
        *(f"      WBSA {t.number} (title from the index)" for t in region.renamed),
        _row("Perspectives boxes", len(boxes.boxes), "PERSP-boxes"),
        _row("  index entries", len(boxes.entries), "PERSP-entries"),
        _row("  notes", found.notes["PERSP"]),
        *(_row(f"  passage: {shape}", found.shapes[shape]) for shape in _BOX_SHAPES
          if found.shapes[shape]),
        *(_row(f"  anchor: {where}", n) for (feature, where), n in sorted(found.anchors.items())
          if feature == "PERSP"),
        *(_row(f"  {what}", n) for what, n in sorted(persp_built.items())),
        *(_row(f"  quotation: {kind}", found.classes.get("PERSP", Counter())[kind])
          for kind in _QUOTE_CLASSES),
        _words(found.words.get("PERSP", [])),
        _row("  index prints another passage", len(boxes.index_differs)),
        *(f"      {b.name} (index: {b.entry.reference if b.entry else '?'})"
          for b in boxes.index_differs),
        _row("anchors outside the passage", len(found.outside)),
        *(f"      {where}" for where in found.outside),
        _row("boxes inside a verse", len(found.mid_verse)),
        *(f"      {where}" for where in found.mid_verse),
        _row("shown before an earlier article", len(found.shown_first)),
        *(f"      {where}" for where in found.shown_first),
        _row("quotations the book edits otherwise", len(found.others)),
        *(f"      {name}" for name in found.others),
        f"  {'ref: links':<34}{len(found.links):>8,}  → {targets:,} targets",
        *(_row(f"  {label}", evidence[key]) for key, label in _EVIDENCE if key != "unexplained"),
        f"  {'  unexplained':<34}{evidence['unexplained']:>8,}  (target 0)",
        _row("broken words joined (items)", found.fixes["letter-spaced"]),
        _row("sentences run together, split", found.fixes["fused-sentences"]),
        _row("compound hyphens restored", found.fixes["compound-hyphens"]),
        "",
        "Topics and Perspectives checks (any failure blocks writing)",
        f"  every callout matched             {_ok(not region.unmatched_callouts)}",
        f"  every topic indexed and placed    {_ok(not region.unindexed)}",
        f"  every box indexed and placed      {_ok(not boxes.unindexed)}",
        f"  index passages explained          {_ok(not found.unexplained_index)}",
        f"  quotations explained              {_ok(not found.unreviewed)}",
        f"  ref: links explained              {_ok(not evidence['unexplained'])}",
        f"  hygiene, flanking, round trip     {_ok(not any(found.hygiene.values()))}",
        f"  parse errors                      "
        f"{_ok(not (found.errors or region.errors or boxes.errors))}",
    ]  # fmt: skip
    problems = [
        *(f"callout without a topic: {c.book} p{c.page}" for c in region.unmatched_callouts),
        *(f"topic without its index entry: p{t.page}" for t in region.unindexed),
        *(f"box without its index entry: {b.name}" for b in boxes.unindexed),
        *(f"index prints another passage: {b.name}" for b in found.unexplained_index),
        *(f"quotation not reviewed: {name}" for name in found.unreviewed),
        *(f"unexplained link: {f.note} {f.link!r} → {', '.join(f.targets)}"
          for f in found.links if f.evidence == "unexplained"),
        *region.errors,
        *boxes.errors,
        *found.errors,
    ]  # fmt: skip
    lines += [f"    ✗ {problem}" for problem in problems[:40]]
    for name, where in found.hygiene.items():
        lines.append(f"    ✗ {name}: {len(where)} — {', '.join(where[:8])}")
    if cross is not None:
        lines += [
            "",
            *cross_summary(
                cross, "Cross-check: topics and boxes, PDF vs EPUB, item by item", headings=False
            ),
        ]
    return lines
