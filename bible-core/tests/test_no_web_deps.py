"""Durable guard for the hard invariant: bible-core declares no web framework.

This survives the shared workspace venv (where FastAPI is physically present because
bible-api pulls it). It enforces the boundary at the level that actually matters and
that a downstream consumer relies on: bible-core's *declared* dependencies. See
docs/SPEC.md §2 and CLAUDE.md (Architecture invariant).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

# Anything web-framework-shaped. Substring match against normalized requirement names.
FORBIDDEN = {"fastapi", "starlette", "uvicorn", "httpx", "flask", "django", "aiohttp"}

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _all_declared_requirements() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data.get("project", {})
    reqs: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        reqs.extend(group)
    for group in data.get("dependency-groups", {}).values():
        reqs.extend(str(item) for item in group)
    return reqs


def test_bible_core_declares_no_web_framework() -> None:
    requirements = _all_declared_requirements()
    offenders = [req for req in requirements if any(banned in req.lower() for banned in FORBIDDEN)]
    assert not offenders, f"bible-core must stay web-free; found: {offenders}"
