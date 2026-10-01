"""The verification summary every run prints (counts and verse references, never text)."""

from __future__ import annotations

from collections import Counter

from emb_convert.crosscheck import CrossCheck, Verdict
from emb_convert.text import ParseResult
from emb_convert.validate import Validation

# The S1 acceptance targets (docs/v8/SPEC.md §3, as corrected by the S1 parse).
EXPECTED: dict[str, int] = {
    "chapters": 1189,
    "verses": 31064,
    "combined": 24,
    "headings": 2196,
    "labels": 59,
    "markers": 4817,
    "perspectives-boxes": 26,
    "italic:psalm-title": 163,
    "italic:psalm-verse-text": 97,
    "italic:sentence-continuation": 15,
    "italic:stanza-label": 22,
    "italic:speaker-label": 37,
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
        f"  hygiene (scraps, *, spacing, fused) {_ok(not any(validation.hygiene.values()))}",
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


def cross_summary(cross: CrossCheck) -> list[str]:
    fixes = Counter(
        name for f in cross.findings if f.verdict is Verdict.FIXED_QUIRK for name in f.fixes
    )
    open_clean = cross.open_in_clean_verses()
    open_damaged = [f for f in cross.findings if f.verdict is Verdict.OPEN and f.epub_damaged]
    regressions = [f for f in cross.findings if f.verdict is Verdict.FIX_REGRESSION]
    headings = Counter(h.kind for h in cross.headings)
    lines = [
        "Cross-check: PDF parse vs EPUB, verse by verse",
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
        f"  {'open, EPUB verse without damage':<34}{len(open_clean):>8,}  (target 0)",
        _row("open, EPUB verse visibly damaged", len(open_damaged)),
    ]
    for f in regressions + open_clean:
        lines.append(f"    ✗ {f.verdict.value} {' '.join(map(str, f.key))} {f.detail}")
    if open_damaged:
        lines.append(
            "    " + ", ".join(f"{b} {c}:{v}" for (b, c, v) in (f.key for f in open_damaged))
        )
    lines += ["", "Headings the two parses don't share"]
    lines += [_row(kind, n) for kind, n in sorted(headings.items())]
    return lines
