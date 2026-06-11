"""Guard against issue #67: section-heading text fused into verse text.

An upstream extraction artifact had glued ~1,800 section headings onto the end of the verse
*before* each new section across the committed translations (and left them out of the
chapter ``headings`` arrays), polluting FTS search and the WEB embeddings. ``scripts/
fix_fused_headings.py`` cleaned the corpus. This test re-applies that script's *detection*
rule to every committed translation and asserts nothing matches — so a future re-extraction
that reintroduces the artifact fails the default gate, not silently ships.

Fast (~1s, pure file read + regex), so it runs in the default unit suite, not integration.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"

# Import the cleaner's detection function so the guard can never drift from the fix.
_spec = importlib.util.spec_from_file_location(
    "fix_fused_headings", REPO_ROOT / "scripts" / "fix_fused_headings.py"
)
assert _spec and _spec.loader
_cleaner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cleaner)
fused_heading = _cleaner.fused_heading

# Kris's original six (issue #67): (book abbr, chapter, verse, heading, before_verse).
ISSUE_67_EXAMPLES = [
    ("Matt", 17, 21, "The Second Prediction of the Passion", 22),
    ("Exod", 19, 15, "The LORD Visits Sinai", 16),
    ("Exod", 34, 9, "The LORD Renews the Covenant", 10),
    ("Deut", 26, 15, "Obey the LORD’s Commands", 16),
    ("Job", 40, 5, "The LORD Challenges Job Again", 6),
    ("Job", 42, 6, "The LORD Rebukes Job’s Friends", 7),
]


def _load(code: str) -> Any:
    return json.loads((TRANSLATIONS / f"{code}.json").read_text(encoding="utf-8"))


def test_no_fused_headings_in_any_translation() -> None:
    """No committed translation verse may end in a fused section heading."""
    offenders: list[str] = []
    for path in sorted(TRANSLATIONS.glob("*.json")):
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        code = data.get("code", path.stem)
        for book in data.get("books", []):
            for chapter in book.get("chapters", []):
                for verse in chapter.get("verses", []):
                    match = fused_heading(verse.get("text", ""))
                    if match is not None:
                        ref = f"{book['abbreviation']} {chapter['number']}:{verse['number']}"
                        offenders.append(f"{code} {ref}: {match.heading!r}")
    assert not offenders, "fused section headings found (issue #67):\n" + "\n".join(offenders[:50])


def test_issue_67_examples_are_cleaned_and_restored() -> None:
    """Each of Kris's six verses: heading stripped from text, restored to the headings array."""
    web: Any = _load("WEB")
    books: Any = {b["abbreviation"]: b for b in web["books"]}
    for abbr, ch, vs, heading, before_verse in ISSUE_67_EXAMPLES:
        chapter = next(c for c in books[abbr]["chapters"] if c["number"] == ch)
        verse = next(v for v in chapter["verses"] if v["number"] == vs)
        assert heading not in verse["text"], f"{abbr} {ch}:{vs} still carries the fused heading"
        assert any(
            h["before_verse"] == before_verse and h["text"] == heading for h in chapter["headings"]
        ), f"{abbr} {ch}: heading {heading!r} missing at before_verse {before_verse}"
