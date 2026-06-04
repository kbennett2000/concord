"""Pydantic v2 response models — the byte-precise SPEC §7 shapes.

Field declaration order is significant: it is the JSON key order clients encode against.
Parallel and grouped are structurally different (the ``translations`` field is a list vs.
a dict, and verse objects differ), so they are separate models; the endpoint dispatches
on ``?format=``.
"""

from __future__ import annotations

from pydantic import BaseModel


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
