"""Runtime configuration, read from the environment.

Two knobs only, so plain ``os.environ`` is enough — no settings dependency for this.
See docs/SPEC.md §3 (operating constraints): the port and CORS origins must both be
env-configurable; hardcoded values are a bug.
"""

from __future__ import annotations

import os

DEFAULT_PORT = 8000
DEFAULT_CORS_ORIGINS = "*"
DEFAULT_DB_PATH = "bible.db"
DEFAULT_TRANSLATION = "KJV"
DEFAULT_SEMANTIC_MAX_CONCURRENCY = 2
_FALSEY = {"0", "false", "no", "off"}


def port() -> int:
    """API port. ``BIBLE_API_PORT`` (default 8000).

    In Docker the container always listens on 8000 and the host port is remapped via
    compose; this is honored when running uvicorn directly (e.g. ``make run``).
    """
    return int(os.environ.get("BIBLE_API_PORT", DEFAULT_PORT))


def cors_origins() -> list[str]:
    """Allowed CORS origins. ``CONCORD_CORS_ORIGINS`` (comma-separated, default ``*``).

    LAN-trusted and read-only, so the default is permissive. The single token ``*``
    means "all origins"; any other value is split into an explicit, trimmed list.
    """
    raw = os.environ.get("CONCORD_CORS_ORIGINS", DEFAULT_CORS_ORIGINS).strip()
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def db_path() -> str:
    """Path to the built ``bible.db``. ``BIBLE_DB_PATH`` (default ``bible.db``)."""
    return os.environ.get("BIBLE_DB_PATH", DEFAULT_DB_PATH)


def default_translation() -> str:
    """Translation used when ``?translations=`` is omitted.

    ``CONCORD_DEFAULT_TRANSLATION`` (default ``KJV``), upper-cased to match stored ids.
    Verified to be loaded at startup; the app refuses to start otherwise.
    """
    return os.environ.get("CONCORD_DEFAULT_TRANSLATION", DEFAULT_TRANSLATION).strip().upper()


def semantic_enabled() -> bool:
    """Whether semantic search is served. ``CONCORD_SEMANTIC_SEARCH`` (default on).

    When on, the app primes the embedding store + model at startup (and refuses to start on
    a model/vectors mismatch). Set it to ``0``/``false``/``no``/``off`` to disable — the
    endpoint then returns 503 and no model is loaded (used by the fast test suite).
    """
    return os.environ.get("CONCORD_SEMANTIC_SEARCH", "1").strip().lower() not in _FALSEY


def semantic_max_concurrency() -> int:
    """Max concurrent semantic-search inferences. ``CONCORD_SEMANTIC_MAX_CONCURRENCY``.

    Default 2, sized to a weak ~2-core non-AVX2 box (≈ one in-flight inference per core);
    excess requests are shed with 503 + Retry-After. Raise it on beefier / AVX2 hardware.
    ``0`` (or any non-positive value) disables the cap entirely. See docs/adr/ADR-0001.
    """
    value = int(
        os.environ.get("CONCORD_SEMANTIC_MAX_CONCURRENCY", DEFAULT_SEMANTIC_MAX_CONCURRENCY)
    )
    return value if value > 0 else 0
