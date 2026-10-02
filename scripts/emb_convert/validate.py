"""Structural and hygiene checks on the parsed text — independent of the EPUB.

- Sequence: every chapter's verse numbers run 1..N against the KJV skeleton, with exactly
  the NLT's omissions and extras (``skeleton.py``) and the combined verses the PDF prints.
- Chapters: 1,189, each book matching both the skeleton and its own chapter-navigation list.
- Hygiene: no markup scraps, ``*``, double spaces, letter-spacing remnants, digits glued to
  words (ordinals like "430th" aside), stray small caps, box reference strings or fused
  headings in any verse. (Callout labels are not scanned for: many are names that verses
  rightly contain, "Herod Antipas"; a leaked label surfaces in the cross-check instead.)
- Punctuation spacing (``PUNCTUATION``, verses and headings; the notes run it too): no word
  run into an opening mark, no space after one, no space before closing punctuation, no
  closing mark run into a word, no number spread digit by digit, no mark run into the " / " of a
  quoted line break.

Any failure here blocks writing ``EMB.json``.
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from emb_convert.skeleton import NLT_EXTRA, NLT_OMITTED, REPO_ROOT
from emb_convert.text import ParseResult

_HYGIENE: dict[str, re.Pattern[str]] = {
    "markup": re.compile(r"[<>]|&\w+;|href|calibre|filepos"),
    "asterisk": re.compile(r"\*"),
    "double-space": re.compile(r"  "),
    "letter-spacing": re.compile(r"(?:^|\s)(?:[A-Za-z] ){2,}[A-Za-z](?:\s|[.,;:!?]|$)"),
    "digit-in-word": re.compile(r"[A-Za-z]\d|\d(?!(?:st|nd|rd|th)\b)[A-Za-z]"),
    "small-caps-fragment": re.compile(r"\bORD\b"),
    "box-reference": re.compile(r"\b[A-Z]{3,} \d+:\d+"),
}

# How a broken-word fix that misjudges a mark, or a gap the text layer kept, shows (the
# 2 Cor 12:1 study note's "word(", docs/dev-notes.md). Each exception is the book's own printing:
# an editorial completion inside a word ("x[s]"), a spaced ellipsis (". . ." and ". . . ,"), a
# word-initial apostrophe ("’tis") and single-letter abbreviations ("B.C.", "i.e.").
PUNCTUATION: dict[str, re.Pattern[str]] = {
    "word-into-opening-mark": re.compile(r"[A-Za-z0-9](?:[(“‘]|\[(?![a-z]+\]))"),
    "space-after-opening-mark": re.compile(r"[(\[“‘] "),
    "space-before-closing-mark": re.compile(r"(?<![.…]) (?:[,;:!?)\]”]|’(?![A-Za-z])|\.(?! \.))"),
    "closing-mark-into-word": re.compile(r"[,;:!?)\]”][A-Za-z]|[A-Za-z]{2}\.[A-Za-z]"),
    "spaced-digits": re.compile(r"(?<![\d,.])\d(?: \d)+(?![\d,])"),
    "mark-into-line-slash": re.compile(r"[,;:.!?—]/ "),  # a quoted line break is " / "
}
_HYGIENE.update(PUNCTUATION)

FUSED_HEADINGS_SCRIPT = REPO_ROOT / "scripts" / "fix_fused_headings.py"


@dataclass(slots=True)
class Validation:
    sequence: list[str] = field(default_factory=list[str])
    chapters: list[str] = field(default_factory=list[str])
    hygiene: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    absorbed: int = 0

    @property
    def ok(self) -> bool:
        return not self.sequence and not self.chapters and not any(self.hygiene.values())


def _fused_heading_check() -> Callable[[str], object | None]:
    """``fused_heading()`` from scripts/fix_fused_headings.py (the issue-#67 detector)."""
    spec = importlib.util.spec_from_file_location("fix_fused_headings", FUSED_HEADINGS_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {FUSED_HEADINGS_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Callable[[str], object | None], cast(Any, module).fused_heading)


def validate(
    result: ParseResult,
    skeleton: dict[tuple[str, int], int],
    fused_heading: Callable[[str], object | None] | None = None,
) -> Validation:
    check = Validation()
    fused = fused_heading or _fused_heading_check()
    italic_text = result.diagnostics.italic_verse_text
    books = {book.code: book for book in result.books}
    expected_books = sorted({book for book, _ in skeleton})
    if sorted(books) != expected_books:
        check.chapters.append(f"books: {len(books)} parsed, {len(expected_books)} expected")

    for code, book in books.items():
        expected = sorted(ch for b, ch in skeleton if b == code)
        got = [chapter.number for chapter in book.chapters]
        if got != expected:
            check.chapters.append(
                f"{code}: chapters {got[:3]}…({len(got)}), {len(expected)} expected"
            )
        nav = result.diagnostics.nav_chapters.get(code)
        if nav is not None and nav != len(got):
            check.chapters.append(f"{code}: navigation list says {nav} chapters, parsed {len(got)}")
        for chapter in book.chapters:
            _check_sequence(check, code, chapter.number, chapter.verses, skeleton)
            headings = [h.text for h in chapter.headings if len(h.text.split()) >= 2]
            for heading in chapter.headings:
                for name, pattern in PUNCTUATION.items():
                    if pattern.search(heading.text):
                        where = f"{code} {chapter.number} heading before {heading.before_verse}"
                        check.hygiene.setdefault(name, []).append(where)
            for verse in chapter.verses:
                ref = f"{code} {chapter.number}:{verse.number}"
                for name, pattern in _HYGIENE.items():
                    if pattern.search(verse.text):
                        check.hygiene.setdefault(name, []).append(ref)
                match = fused(verse.text)
                tail = cast(str, getattr(match, "heading", "")) if match is not None else ""
                if any(h in verse.text for h in headings) or (match and tail not in italic_text):
                    check.hygiene.setdefault("fused-heading", []).append(ref)
    return check


def _check_sequence(
    check: Validation,
    code: str,
    chapter: int,
    verses: list[Any],
    skeleton: dict[tuple[str, int], int],
) -> None:
    present: list[int] = []
    for verse in verses:
        present.append(verse.number)
        absorbed = list(range(verse.number + 1, verse.last + 1))
        check.absorbed += len(absorbed)
        present.extend(absorbed)
    count = skeleton.get((code, chapter), 0)
    expected = [
        n
        for n in range(1, count + 2)
        if (n <= count and (code, chapter, n) not in NLT_OMITTED) or (code, chapter, n) in NLT_EXTRA
    ]
    if present != expected:
        missing = sorted(set(expected) - set(present))
        extra = sorted(set(present) - set(expected))
        order = present != sorted(set(present))
        check.sequence.append(
            f"{code} {chapter}: missing {missing[:5]} extra {extra[:5]}"
            + (" (out of order or repeated)" if order else "")
        )
