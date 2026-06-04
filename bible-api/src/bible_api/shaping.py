"""Turn a ``QueryResult`` into either response shape.

Shared by both endpoints — the reason Slice 4 is one combined cycle. Both shapes are
produced from the same flat rows, so the two endpoints never duplicate this logic.
"""

from __future__ import annotations

from bible_core.queries import QueryResult

from .schemas import (
    GroupedVerse,
    ParallelVerse,
    VerseResponseGrouped,
    VerseResponseParallel,
)


def shape_parallel(result: QueryResult) -> VerseResponseParallel:
    """One object per verse position; each requested translation's text or ``null``."""
    by_position: dict[tuple[int, int], dict[str, str]] = {}
    for row in result.rows:
        by_position.setdefault((row.chapter, row.verse), {})[row.translation_id] = row.text

    verses = [
        ParallelVerse(
            book=result.book_id,
            chapter=chapter,
            verse=verse,
            reference=f"{result.book_name} {chapter}:{verse}",
            text={tid: by_position[(chapter, verse)].get(tid) for tid in result.translations},
        )
        for chapter, verse in sorted(by_position)
    ]
    return VerseResponseParallel(
        reference=result.reference,
        translations=list(result.translations),
        verses=verses,
    )


def shape_grouped(result: QueryResult) -> VerseResponseGrouped:
    """Verses bucketed by translation id; every requested id is present (possibly empty)."""
    groups: dict[str, list[GroupedVerse]] = {tid: [] for tid in result.translations}
    for row in sorted(result.rows, key=lambda r: (r.chapter, r.verse)):
        groups[row.translation_id].append(
            GroupedVerse(book=row.book_id, chapter=row.chapter, verse=row.verse, text=row.text)
        )
    return VerseResponseGrouped(reference=result.reference, translations=groups)
