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

from __future__ import annotations

from pathlib import Path

import pytest

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
