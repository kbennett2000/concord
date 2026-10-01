"""Regression guard for the dual-ignore invariant (SPEC v4 §2, ADR-0004).

Any directory holding copyrighted / non-redistributable data MUST be in **both** ``.gitignore``
AND ``.dockerignore``. The Dockerfile's broad ``COPY data/ data/`` is not selective — the
``.dockerignore`` exclusion is the only thing keeping restricted data (private translations and
private translator's notes) out of the build context and the baked ``bible.db``. Private notes
live under ``data/private/notes/``, already covered by the ``data/private/`` rule; this test
fails loudly if either rule is ever removed.

The mirror image (ADR-0004): the **committed public** notes path ``data/notes/`` is meant to
*ship*, so it must stay OUT of both ignore files — this test also fails loudly if it ever gets
ignored, which would silently drop the public-domain notes from the image.

Complements ``test_notes_loader.test_clean_build_bakes_public_notes_but_zero_private_notes``,
which proves the *behavior* (a clean build bakes public notes, zero private notes); this proves
the *ignore-file* guards that keep the clean build clean and the public path shippable.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import _default_data_dirs, build_database
from loaderkit import book, chapter, translation, verse, write_translation

REPO_ROOT = Path(__file__).resolve().parents[2]


def _ignore_lines(name: str) -> set[str]:
    path = REPO_ROOT / name
    assert path.is_file(), f"{name} is missing at the repo root."
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


@pytest.mark.parametrize("ignore_file", [".gitignore", ".dockerignore"])
def test_private_data_dir_is_ignored(ignore_file: str) -> None:
    assert "data/private/" in _ignore_lines(ignore_file), (
        f"data/private/ must stay in {ignore_file} — it is the only barrier keeping "
        "copyrighted translations and translator's notes out of the repo and the image."
    )


@pytest.mark.parametrize("ignore_file", [".gitignore", ".dockerignore"])
def test_public_notes_dir_is_not_ignored(ignore_file: str) -> None:
    """The mirror guard (ADR-0004): the committed public notes path must SHIP. If it ever lands
    in an ignore file, the public-domain notes silently vanish from the repo and the image."""
    lines = _ignore_lines(ignore_file)
    offenders = {entry for entry in lines if entry.rstrip("/") == "data/notes"}
    assert not offenders, (
        f"data/notes/ must NOT be in {ignore_file} — it is the committed public-domain notes "
        f"path that ships in the image (ADR-0004). Found: {offenders}."
    )


def _build(base: Path) -> list[str]:
    """Build from the directories the loader's CLI picks under ``base``; list the baked ids."""
    db = base / "bible.db"
    build_database(db, _default_data_dirs(base))
    with sqlite3.connect(db) as conn:
        return [row[0] for row in conn.execute("SELECT id FROM translations ORDER BY id")]


def _one_verse(code: str) -> dict[str, object]:
    return translation(code, [book("Gen", 1, [chapter(1, [verse(1, "Made-up words.")])])])


def test_clean_checkout_bakes_zero_private_translations(tmp_path: Path) -> None:
    """A clean checkout has no data/private/: only committed translations are baked. This is
    what keeps an operator's private study Bible (v8: data/private/EMB.json) out of any build
    made from the repository alone."""
    write_translation(tmp_path / "translations", _one_verse("PUB"))
    assert _build(tmp_path) == ["PUB"]


def test_local_private_translations_are_added_only_when_present(tmp_path: Path) -> None:
    write_translation(tmp_path / "translations", _one_verse("PUB"))
    write_translation(tmp_path / "private", _one_verse("PRIV"))
    write_translation(tmp_path / "private" / "work" / "PRIV", _one_verse("WORK"))
    # work/ files (the v8 converter's markers and reports) are never scanned as translations
    assert _build(tmp_path) == ["PRIV", "PUB"]
