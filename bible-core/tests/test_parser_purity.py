"""The parser is pure: parser.py imports nothing that does I/O or web work."""

from __future__ import annotations

import ast
from pathlib import Path

import bible_core.parser as parser_module

FORBIDDEN = {
    "sqlite3",
    "json",
    "pathlib",
    "os",
    "io",
    "socket",
    "http",
    "urllib",
    "requests",
    "httpx",
    "fastapi",
    "starlette",
}


def _top_level_imports(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_parser_module_has_no_io_or_web_imports() -> None:
    source = Path(parser_module.__file__).read_text(encoding="utf-8")
    offenders = _top_level_imports(source) & FORBIDDEN
    assert not offenders, f"parser.py must stay pure; found imports: {sorted(offenders)}"
