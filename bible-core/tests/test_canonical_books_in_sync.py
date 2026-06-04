"""The vendored package-data copy must stay byte-identical to the docs source of truth.

`docs/canonical-books.md` is the human source of truth; `bible-core` ships its own copy
so it is self-contained when imported in-process. This guard fails the moment they drift.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_COPY = REPO_ROOT / "docs" / "canonical-books.md"


def test_packaged_copy_matches_docs() -> None:
    packaged = files("bible_core").joinpath("data/canonical-books.md").read_bytes()
    docs = DOCS_COPY.read_bytes()
    assert packaged == docs, (
        "bible-core/src/bible_core/data/canonical-books.md has drifted from "
        "docs/canonical-books.md — re-copy the docs version into the package."
    )
