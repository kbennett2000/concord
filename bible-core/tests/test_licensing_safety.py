"""Regression guard for the dual-ignore invariant (SPEC v4 §2).

Any directory holding copyrighted / non-redistributable data MUST be in **both** ``.gitignore``
AND ``.dockerignore``. The Dockerfile's broad ``COPY data/ data/`` is not selective — the
``.dockerignore`` exclusion is the only thing keeping restricted data (private translations and
now translator's notes) out of the build context and the baked ``bible.db``. Notes live under
``data/private/notes/``, already covered by the ``data/private/`` rule; this test fails loudly if
either rule is ever removed.

Complements ``test_notes_loader.test_clean_build_with_no_private_data_yields_zero_notes``, which
proves the *behavior* (a clean build bakes zero notes); this proves the *ignore-file* guard that
keeps the clean build clean.
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
