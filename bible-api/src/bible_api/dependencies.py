"""Request-scoped dependencies: the DB connection and translation-set resolution."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from bible_core.db import connect_readonly
from fastapi import Request

from .errors import UnknownTranslationError


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """Yield a per-request read-only connection to the configured ``bible.db``."""
    conn = connect_readonly(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def resolve_translations(request: Request, translations: str | None) -> tuple[str, ...]:
    """Resolve ``?translations=`` to a validated, de-duplicated, upper-cased id tuple.

    Omitted/blank → the configured default. Unknown ids → ``UnknownTranslationError``
    (404). Order and duplicates from the request are preserved/collapsed.
    """
    loaded: set[str] = request.app.state.translations
    default: str = request.app.state.default_translation

    if translations is None or not translations.strip():
        return (default,)

    resolved: list[str] = []
    seen: set[str] = set()
    for raw in translations.split(","):
        tid = raw.strip().upper()
        if not tid:
            continue
        if tid not in loaded:
            raise UnknownTranslationError(tid, list(loaded))
        if tid not in seen:
            seen.add(tid)
            resolved.append(tid)

    return tuple(resolved) if resolved else (default,)


def resolve_translation(request: Request, translation: str | None) -> str:
    """Resolve a single ``?translation=`` to a validated, upper-cased id.

    Search is single-translation (SPEC §3). Omitted/blank → the configured default.
    Anything not loaded (including a comma'd value like ``kjv,web``) → 404.
    """
    loaded: set[str] = request.app.state.translations
    default: str = request.app.state.default_translation

    if translation is None or not translation.strip():
        return default

    tid = translation.strip().upper()
    if tid not in loaded:
        raise UnknownTranslationError(tid, list(loaded))
    return tid
