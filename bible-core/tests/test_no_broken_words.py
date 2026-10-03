"""Guard against words broken by a stray space, or glued together, in the committed text.

The committed English translations carried their source text layer's word breaks ("in t he
ark", "sin- offering", "father’ s") and a few glued words ("himboth", "Damascus.Behold") until
``scripts/fix_broken_words.py`` repaired them; every change is a row of
``scripts/broken_words_manifest.csv``. These tests re-apply that script's own detection, so a
re-extraction that brings the breaks back fails the gate instead of shipping.

The default run uses ``quick_check``: lone letters and hyphen spaces, the commonest kinds, in a
few seconds. The full detector takes about a minute over the corpus, so it is an integration test.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
from fix_broken_words import Corpus, TranslationFile, detect, quick_check

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"

# (translation, reference, text the repaired verse holds), one per kind of repair
REPAIRED = [
    ("KJV", "Gen 6:14", "in the ark,"),  # "in t he ark"
    ("WEB", "Exod 26:18", "the tabernacle,"),  # "tabernacl e,"
    ("ASV", "Lev 4:34", "sin-offering with"),  # "sin- offering"
    ("DRB", "Jer 3:25", "against the Lord"),  # "theLord"
    ("ASV", "Isa 17:1", "Damascus. Behold,"),  # "Damascus.Behold"
]


@cache
def _english() -> tuple[TranslationFile, ...]:
    files = (TranslationFile(p) for p in sorted(TRANSLATIONS.glob("*.json")))
    return tuple(f for f in files if f.english)


def test_no_lone_letter_breaks_or_hyphen_spaces_in_any_translation() -> None:
    offenders = [
        f"{f.code} {f.labels[ref]}: {span!r}"
        for f in _english()
        for ref, span in quick_check(f.verses)
    ]
    assert not offenders, "broken words (scripts/fix_broken_words.py):\n" + "\n".join(
        offenders[:50]
    )


def test_the_repaired_examples_read_right() -> None:
    files = {f.code: f for f in _english()}
    for code, label, expected in REPAIRED:
        verses = files[code]
        ref = next(r for r, name in verses.labels.items() if name == label)
        assert expected in verses.verses[ref], f"{code} {label}: {verses.verses[ref]!r}"


@pytest.mark.integration
def test_the_full_detector_finds_nothing_left_to_repair() -> None:
    files = _english()
    found = detect(Corpus({f.code: f.verses for f in files}))
    labels = {f.code: f.labels for f in files}
    pending = [f"{c.code} {labels[c.code][c.ref]} {c.kind}: {c.before!r}" for c in found.changes]
    assert not pending, "repairs left to make (run the script):\n" + "\n".join(pending[:50])
