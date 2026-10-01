"""PDF-vs-EPUB verse cross-check: every disagreement gets exactly one class.

Three parses meet here: the fixed PDF parse (what ships), the raw PDF parse (no quirk fixes)
and the EPUB parse (a damaged, independent witness). A verse is classed by its worst
difference:

- AGREE — fixed PDF = EPUB (and raw = EPUB).
- FIXED_QUIRK — raw ≠ EPUB, fixed = EPUB: a quirk fix made them agree.
- FIX_REGRESSION — raw = EPUB, fixed ≠ EPUB: a fix broke a verse. Target 0; each is a bug.
- OPEN — a difference no evidence explains: PDF-only words with nothing at that spot (how
  a leaked callout, box line, intro text or italic label would surface), EPUB-only words
  that aren't scraps or splices, unexplained substitutions.
- EPUB_VISIBLE — the EPUB shows damage where they differ: a markup scrap, a non-word
  ("laydi", a stray "m"), digits fused into a word, or the EPUB lacks the verse.
- EPUB_SPLICE — EPUB-only words that belong elsewhere: a PDF heading of this chapter run
  into the verse, or a fragment the PDF prints elsewhere in the book that the operator's
  NLT doesn't have in this verse.
- EPUB_LOSS — PDF-only words with evidence at that spot: the EPUB left a dropped-text
  break there (an empty anchor), fused the neighbouring words into one token, or the
  operator's NLT has the same words in this verse.
- SPELLING — the same word hyphenated on one side only ("cup-bearer"/"cupbearer"); the
  PDF page prints its form (checked by rendering), so the PDF text is faithful.
- VERIFIED — would be OPEN, but the rendered PDF page was checked by eye and prints the
  words in the verse's own text flow; the EPUB lost them without a trace. References only,
  in ``VERIFIED_ON_PAGE`` (docs/dev-notes.md, V8-S1).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum

from emb_convert.epub import BREAK, EpubBible
from emb_convert.skeleton import NLT_EXTRA

Key = tuple[str, int, int]

_WS = re.compile(r"\s+")
_SCRAP = re.compile(r"[<>=]|&\w+;|calibre|filepos|\d[A-Za-z]|[A-Za-z]\d|[A-Za-z][“”\"][A-Za-z]")
_BRACKETS = re.compile(r"[()\[\]“”‘’\"']+")
_NUMBER = re.compile(r"\d[\d,:\-–]*")
_LOOSE = re.compile(r"[^\w\s]")
_LETTERS = re.compile(r"[^a-z’']")
_FRACTION = re.compile("[¼-¾⅐-⅞]")
CELL_SEPARATOR = " - "
WORD_LETTERS = frozenset({"a", "i", "o"})


class Verdict(Enum):
    AGREE = "agree"
    FIXED_QUIRK = "fixed-pdf-quirk"
    FIX_REGRESSION = "fix-regression"
    OPEN = "open"
    EPUB_VISIBLE = "epub-damage-visible"
    EPUB_SPLICE = "epub-splice"
    EPUB_LOSS = "epub-loss-with-evidence"
    SPELLING = "hyphenation-variant"
    VERIFIED = "pdf-page-verified"


# PDF-only words the EPUB dropped without a trace, each checked on the rendered PDF page.
VERIFIED_ON_PAGE: frozenset[Key] = frozenset(
    {
        ("EZK", 7, 8),
        ("EZK", 16, 39),
        ("JER", 26, 12),
        ("NUM", 15, 2),
        ("PSA", 11, 1),
        ("PSA", 62, 1),
        ("PSA", 106, 43),
        ("PSA", 132, 1),
    }
)

# Severity order for a verse with several differences: the worst one names the verse.
_SEVERITY = [
    Verdict.OPEN,
    Verdict.EPUB_VISIBLE,
    Verdict.EPUB_SPLICE,
    Verdict.EPUB_LOSS,
    Verdict.SPELLING,
]


@dataclass(frozen=True, slots=True)
class Finding:
    key: Key
    verdict: Verdict
    detail: str
    epub_damaged: bool
    fixes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HeadingFinding:
    chapter: tuple[str, int]
    kind: str  # damaged-in-epub · epub-misnumbered · run-into-epub-verse · missing-in-epub · open


@dataclass(slots=True)
class CrossCheck:
    findings: list[Finding] = field(default_factory=list[Finding])
    headings: list[HeadingFinding] = field(default_factory=list[HeadingFinding])

    def count(self, verdict: Verdict) -> int:
        return sum(1 for f in self.findings if f.verdict is verdict)

    def open_in_clean_verses(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict is Verdict.OPEN and not f.epub_damaged]


def normalize(text: str, *, keep_breaks: bool = False) -> str:
    """Both sides' common form for equality.

    Fractions fold to "n/d": the EPUB prints 7½ as "71/2" (the same small-digit quirk), so
    it cannot witness how a fraction is rendered. Table cell separators and ``*`` go; EPUB
    break sentinels become their own token when ``keep_breaks``, else vanish.
    """
    text = unicodedata.normalize("NFC", text).replace("*", "")
    text = text.replace(BREAK, f" {BREAK} " if keep_breaks else " ")
    text = text.replace(CELL_SEPARATOR, " ")
    text = _FRACTION.sub(
        lambda m: unicodedata.normalize("NFKD", m.group(0)).replace("⁄", "/"), text
    )
    return _WS.sub(" ", text).strip()


def _loose(text: str) -> str:
    return _WS.sub(" ", _LOOSE.sub(" ", text.lower())).strip()


def is_scrap(token: str) -> bool:
    return bool(_SCRAP.search(token)) or bool(_BRACKETS.fullmatch(token))


@dataclass(frozen=True, slots=True)
class Context:
    """What the classifier knows about the PDF as a whole."""

    vocabulary: frozenset[str]
    corpus: str  # every PDF verse, normalized, space-padded
    headings: dict[tuple[str, int], frozenset[str]]
    labels: dict[tuple[str, int], frozenset[str]]  # callout labels the PDF parse set aside
    pages: dict[int, str]  # every PDF page's raw text, loose-normalized
    spans: dict[Key, tuple[int, int]]  # each verse's PDF pages

    @classmethod
    def build(
        cls,
        fixed: dict[Key, str],
        headings: dict[tuple[str, int], list[str]],
        labels: list[tuple[str, int, str]],
        pages: dict[int, str],
        spans: dict[Key, tuple[int, int]],
    ) -> Context:
        texts = [normalize(t) for t in fixed.values()]
        vocabulary = frozenset(_word(t) for text in texts for t in text.split(" ") if _word(t))
        return cls(
            vocabulary=vocabulary,
            corpus=f" {' '.join(texts)} ",
            headings={ch: frozenset(normalize(h) for h in hs) for ch, hs in headings.items()},
            labels={
                (code, ch): frozenset(normalize(t) for c, n, t in labels if (c, n) == (code, ch))
                for code, ch, _ in labels
            },
            pages={page: f" {_loose(normalize(text))} " for page, text in pages.items()},
            spans=spans,
        )

    def on_pdf_pages(self, key: Key, words: list[str]) -> bool:
        """Is ``words`` (in order) printed on the verse's PDF pages (± one)?"""
        first, last = self.spans.get(key, (0, 0))
        if not first:
            return True  # unknown span: assume it could be, so nothing is excused
        needle = f" {_loose(' '.join(words))} "
        return any(needle in self.pages.get(p, "") for p in range(first - 1, last + 2))


def _word(token: str) -> str:
    return _LETTERS.sub("", token.lower())


def _non_word(token: str, vocabulary: frozenset[str]) -> bool:
    word = _word(token)
    if not word:
        return False
    if len(word) == 1:
        return word not in WORD_LETTERS
    return word not in vocabulary


def _subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(ch in it for ch in short)


def _in_nlt(words: Sequence[str], nlt_text: str | None) -> bool:
    if not nlt_text or not words:
        return False
    needle = _loose(" ".join(words))
    return bool(needle) and f" {needle} " in f" {_loose(nlt_text)} "


def _epub_tokens(epub: str) -> tuple[list[str], set[int]]:
    """EPUB tokens without break sentinels, and the token indexes a break precedes."""
    tokens: list[str] = []
    breaks: set[int] = set()
    for token in normalize(epub, keep_breaks=True).split(" "):
        if token == BREAK:
            breaks.add(len(tokens))
        elif token:
            tokens.append(token)
    return tokens, breaks


def explain(
    key: Key, pdf: str, epub: str, nlt_text: str | None, ctx: Context
) -> tuple[Verdict, str]:
    """Classify one verse where the fixed PDF and the EPUB differ (both present)."""
    a = normalize(pdf).split(" ")
    b, breaks = _epub_tokens(epub)
    headings = ctx.headings.get(key[:2], frozenset()) | ctx.labels.get(key[:2], frozenset())
    verdicts: list[Verdict] = []
    reasons: list[str] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        pdf_words, epub_words = a[i1:i2], b[j1:j2]
        verdict, reason = _explain_op(
            key, op, pdf_words, epub_words, b[max(j1 - 1, 0) : j2 + 1],
            a[max(i1 - 1, 0) : i1], a[i2 : i2 + 1], breaks, j1, j2, nlt_text, headings, ctx,
        )  # fmt: skip
        verdicts.append(verdict)
        reasons.append(f"{reason}@{i1}")
    worst = min(verdicts, key=_SEVERITY.index) if verdicts else Verdict.EPUB_LOSS
    return worst, " ".join(reasons)


def _explain_op(
    key: Key,
    op: str,
    pdf_words: list[str],
    epub_words: list[str],
    beside: list[str],
    pdf_left: list[str],
    pdf_right: list[str],
    breaks: set[int],
    j1: int,
    j2: int,
    nlt_text: str | None,
    headings: frozenset[str],
    ctx: Context,
) -> tuple[Verdict, str]:
    if op == "replace" and len(pdf_words) == len(epub_words) == 1:
        p, e = pdf_words[0], epub_words[0]
        if e.replace("-", "") == p or p.replace("-", "") == e:
            return Verdict.SPELLING, "hyphen"
    if any(is_scrap(t) or _non_word(t, ctx.vocabulary) for t in epub_words):
        return Verdict.EPUB_VISIBLE, "scrap"
    if any(_NUMBER.fullmatch(t.strip(",.;:")) for t in epub_words) and not pdf_words:
        return Verdict.EPUB_VISIBLE, "stray-number"  # a number the PDF verse doesn't print
    if op == "delete" and any(is_scrap(t) for t in beside):
        return Verdict.EPUB_VISIBLE, "scrap-beside"
    if pdf_words and any(j in breaks for j in range(j1, j2 + 1)):
        return Verdict.EPUB_LOSS, "break"
    fused_text, pdf_text = "".join(epub_words), "".join(pdf_words)
    if op == "replace" and len(fused_text) < len(pdf_text) and _subsequence(fused_text, pdf_text):
        return Verdict.EPUB_LOSS, "fused"
    if pdf_words and _in_nlt(pdf_words, nlt_text):
        return Verdict.EPUB_LOSS, "nlt"
    if epub_words and not pdf_words and _in_nlt(pdf_left + pdf_right, nlt_text):
        # the operator's NLT has the PDF's two neighbouring words side by side here
        return Verdict.EPUB_SPLICE, "nlt-context"
    if epub_words and not ctx.on_pdf_pages(key, pdf_left + epub_words + pdf_right):
        # the EPUB's words, between the PDF's neighbours, are printed nowhere on the verse's
        # PDF pages: the PDF parse can't have dropped them
        return Verdict.EPUB_SPLICE, "not-on-pdf-page"
    if (epub_words and not pdf_words) or op == "replace":
        fragment = " ".join(epub_words)
        if any(fragment == h or (len(epub_words) >= 2 and fragment in h) for h in headings):
            return Verdict.EPUB_SPLICE, "heading-or-callout"
        if (
            len(epub_words) >= 2
            and f" {fragment} " in ctx.corpus
            and not _in_nlt(epub_words, nlt_text)
        ):
            return Verdict.EPUB_SPLICE, "elsewhere"
    return Verdict.OPEN, op


def cross_check(
    fixed: dict[Key, str],
    raw: dict[Key, str],
    solo: dict[str, dict[Key, str]],
    epub: EpubBible,
    nlt: dict[Key, str] | None,
    absorbed: set[Key],
    pdf_headings: dict[tuple[str, int], list[str]],
    skeleton: dict[tuple[str, int], int],
    callout_labels: list[tuple[str, int, str]],
    pages: dict[int, str],
    spans: dict[Key, tuple[int, int]],
) -> CrossCheck:
    """Compare every verse and every chapter's headings; classify each disagreement."""
    ctx = Context.build(fixed, pdf_headings, callout_labels, pages, spans)
    result = CrossCheck()
    for key in sorted(fixed.keys() | epub.verses.keys()):
        damaged = key in epub.damaged
        if key not in epub.verses or not normalize(epub.verses[key]):
            result.findings.append(Finding(key, Verdict.EPUB_VISIBLE, "missing in EPUB", True))
            continue
        e = normalize(epub.verses[key])
        damaged = damaged or any(
            is_scrap(t) or _non_word(t, ctx.vocabulary) for t in e.split(" ") if t
        )
        if key not in fixed:
            beyond = key[:2] not in skeleton or (
                key[2] > skeleton[key[:2]] and key not in NLT_EXTRA
            )
            if key in absorbed:
                verdict, detail = Verdict.EPUB_VISIBLE, "absorbed by a combined verse"
            elif beyond:
                verdict, detail = Verdict.EPUB_VISIBLE, "EPUB numbering past the chapter"
            else:
                verdict = Verdict.EPUB_VISIBLE if damaged else Verdict.OPEN
                detail = "missing in PDF"
            result.findings.append(Finding(key, verdict, detail, damaged))
            continue
        result.findings.append(
            _compare(
                key,
                fixed[key],
                raw.get(key, ""),
                solo,
                epub.verses[key],
                damaged,
                (nlt or {}).get(key),
                ctx,
                VERIFIED_ON_PAGE,
            )  # fmt: skip
        )

    result.headings = _check_headings(pdf_headings, epub, skeleton)
    return result


def _compare(
    key: Key,
    pdf: str,
    pdf_raw: str,
    solo: dict[str, dict[Key, str]],
    epub: str,
    damaged: bool,
    nlt_text: str | None,
    ctx: Context,
    verified: frozenset[Key],
) -> Finding:
    """One text the PDF and the EPUB both have: agree, a fix's doing, or ``explain``'s class."""
    f, r, e = normalize(pdf), normalize(pdf_raw), normalize(epub)
    changed_by = tuple(
        name for name, texts in sorted(solo.items()) if normalize(texts.get(key, "")) != r
    )
    if f == e:
        verdict = Verdict.AGREE if r == e else Verdict.FIXED_QUIRK
        return Finding(key, verdict, "", damaged, changed_by)
    if r == e:
        return Finding(key, Verdict.FIX_REGRESSION, "raw parse agreed", damaged, changed_by)
    verdict, detail = explain(key, pdf, epub, nlt_text, ctx)
    if verdict is Verdict.OPEN and key in verified:
        verdict = Verdict.VERIFIED
    return Finding(key, verdict, detail, damaged, changed_by)


# The EPUB's span soup leaves spaces the book doesn't print: before closing punctuation
# ("10:13 )."), around an em dash, inside a reference split by its link ("2: 5-12",
# "1:22 -25"), around a fraction's slash ("1 / 10"). Both sides close them up alike, so no word
# difference can hide behind it.
_SPACE_BEFORE = re.compile(r"\s+(?=[.,;:!?)\]”’—])")
_SPACE_AFTER = re.compile(r"(?<=[(\[“—])\s+")
_IN_NUMBER = re.compile(r"(?<=\d)\s*([/:\-–])\s*(?=\d)")


def tidy(text: str) -> str:
    return _IN_NUMBER.sub(r"\1", _SPACE_AFTER.sub("", _SPACE_BEFORE.sub("", text)))


def _tidy_all(texts: dict[Key, str]) -> dict[Key, str]:
    return {key: tidy(text) for key, text in texts.items()}


def cross_check_notes(
    fixed: dict[Key, str],
    raw: dict[Key, str],
    solo: dict[str, dict[Key, str]],
    epub: dict[Key, str],
    epub_damaged: set[Key],
    context_texts: dict[Key, str],
    pages: dict[int, str],
    spans: dict[Key, tuple[int, int]],
    verified: frozenset[Key] = frozenset(),
) -> CrossCheck:
    """The notes' text, PDF vs EPUB, with the verses' classes and evidence rules (V8-S2b).

    Keys name notes, not verses. ``context_texts``: every PDF text the evidence may draw on
    (the verses and the notes) — the vocabulary a "non-word" is judged against, and the corpus
    a splice is found in. There is no NLT evidence for notes.
    """
    fixed, raw, epub = _tidy_all(fixed), _tidy_all(raw), _tidy_all(epub)
    solo = {name: _tidy_all(texts) for name, texts in solo.items()}
    ctx = Context.build(context_texts, {}, [], pages, spans)
    result = CrossCheck()
    for key in sorted(fixed.keys() | epub.keys()):
        damaged = key in epub_damaged
        text = epub.get(key, "")
        if not normalize(text):
            result.findings.append(Finding(key, Verdict.EPUB_VISIBLE, "missing in EPUB", True))
            continue
        damaged = damaged or any(
            is_scrap(t) or _non_word(t, ctx.vocabulary) for t in normalize(text).split(" ") if t
        )
        if key not in fixed:
            verdict = Verdict.EPUB_VISIBLE if damaged else Verdict.OPEN
            result.findings.append(Finding(key, verdict, "missing in PDF", damaged))
            continue
        result.findings.append(
            _compare(key, fixed[key], raw.get(key, ""), solo, text, damaged, None, ctx, verified)
        )
    return result


HEADING_SIMILAR = 0.6


def _check_headings(
    pdf_headings: dict[tuple[str, int], list[str]],
    epub: EpubBible,
    skeleton: dict[tuple[str, int], int],
) -> list[HeadingFinding]:
    """Classify every heading the two parses don't share, chapter by chapter.

    An EPUB-only heading that resembles a PDF-only one in the same chapter is that heading
    damaged by the EPUB's conversion; one in a chapter the skeleton lacks is the EPUB's
    misnumbering. A PDF-only heading the EPUB ran into a verse's text, or simply lacks, is
    EPUB loss. Any other EPUB-only heading is OPEN (a heading the PDF parse may have missed).
    """
    found: list[HeadingFinding] = []
    by_book: dict[str, set[str]] = {}
    for (book, _), headings in pdf_headings.items():
        by_book.setdefault(book, set()).update(normalize(h) for h in headings)
    for chapter in sorted(pdf_headings.keys() | epub.headings.keys()):
        pdf_only = [normalize(h) for h in pdf_headings.get(chapter, [])]
        epub_only: list[str] = []
        for heading in (normalize(h) for h in epub.headings.get(chapter, [])):
            if heading in pdf_only:
                pdf_only.remove(heading)
            else:
                epub_only.append(heading)
        for heading in epub_only:
            match = max(
                pdf_only,
                key=lambda h: SequenceMatcher(None, h, heading).ratio(),
                default=None,
            )
            if match is not None and (
                match in heading or SequenceMatcher(None, match, heading).ratio() >= HEADING_SIMILAR
            ):
                pdf_only.remove(match)
                found.append(HeadingFinding(chapter, "damaged-in-epub"))
            elif (
                chapter not in skeleton
                or chapter not in pdf_headings
                or any(  # the PDF's heading of another chapter (perhaps damaged too)
                    SequenceMatcher(None, h, heading).ratio() >= HEADING_SIMILAR
                    for h in by_book.get(chapter[0], set())
                )
            ):
                found.append(HeadingFinding(chapter, "epub-misnumbered"))
            else:
                found.append(HeadingFinding(chapter, "open"))
        chapter_text = " ".join(
            normalize(t) for (b, c, _), t in epub.verses.items() if (b, c) == chapter
        )
        for heading in pdf_only:
            kind = "run-into-epub-verse" if heading in chapter_text else "missing-in-epub"
            found.append(HeadingFinding(chapter, kind))
    return found
