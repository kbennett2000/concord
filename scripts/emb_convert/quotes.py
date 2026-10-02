"""A quotation of Scripture against EMB's own verse text (V8-S3b; docs/v8/SPEC.md §4.2).

What the Bible Says About topics and Perspectives boxes quote the Bible. The book trims and
edits a quotation so it stands alone: it leaves out an opening word or a psalm title, starts
or stops inside a verse, adds a speaker in brackets or puts its own word in brackets for
some of the verse's ("[a name]" for "he"), marks an omission with ". . .". So a quotation is
compared word by word with the verse text of its reference, its bracketed words aside, and
gets one class; an ellipsis or a bracketed word may stand between two parts of it. An
``other`` is listed by reference and must be one the converter's reviewed set names
(``notes.QUOTES_AS_PRINTED``).
"""

from __future__ import annotations

import re
from enum import Enum


class QuoteClass(Enum):
    IDENTICAL = "identical"
    SAME_WORDS = "the same words"
    PART = "a part of the verse text"
    JOINED = "parts joined by an ellipsis or a bracketed word"
    OTHER = "other word changes"


_BRACKETED = re.compile(r"\[[^\]]*\]")
_GAP = re.compile(r"\.\s*\.\s*\.|…|\[[^\]]*\]")  # an omission, or the book's word for some
_WORD = re.compile(r"[A-Za-z0-9’']+")


def words(text: str) -> list[str]:
    """Lower-case words, a straight apostrophe read as a curly one."""
    return [w.lower().replace("'", "’") for w in _WORD.findall(_BRACKETED.sub(" ", text))]


def _find(part: list[str], whole: list[str], start: int = 0) -> int:
    """Where ``part`` runs contiguously in ``whole`` from ``start`` on, else -1."""
    size = len(part)
    for i in range(start, len(whole) - size + 1):
        if whole[i : i + size] == part:
            return i
    return -1


def classify(quoted: str, verses: str) -> QuoteClass:
    """The quotation's class against the verse text it cites."""
    if quoted == verses:
        return QuoteClass.IDENTICAL
    mine, theirs = words(quoted), words(verses)
    if mine == theirs:
        return QuoteClass.SAME_WORDS
    if mine and _find(mine, theirs) != -1:
        return QuoteClass.PART
    segments = [words(s) for s in _GAP.split(quoted)]
    segments = [s for s in segments if s]
    if len(segments) > 1:
        at = 0
        for segment in segments:
            found = _find(segment, theirs, at)
            if found == -1:
                return QuoteClass.OTHER
            at = found + len(segment)
        return QuoteClass.JOINED
    return QuoteClass.OTHER
