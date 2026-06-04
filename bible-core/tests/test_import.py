"""bible-core imports cleanly and exposes a version."""

from __future__ import annotations

import bible_core


def test_version_is_exposed() -> None:
    assert isinstance(bible_core.__version__, str)
    assert bible_core.__version__
