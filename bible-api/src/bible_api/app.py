"""FastAPI application factory, startup DB verification, and ``/healthz``.

On startup the app opens the configured ``bible.db`` read-only, verifies the schema, and
caches the loaded-translation set + counts on ``app.state`` (the corpus is immutable, so
this is computed once). It **refuses to start** if the DB is missing/incompatible or if
the configured default translation isn't loaded — operator misconfiguration surfaces
immediately rather than as confusing 404s later.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import bible_core
import structlog
from bible_core.db import connect_readonly
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__, config
from .errors import register_error_handlers
from .routers import router as v1_router

router = APIRouter()


def _configure_logging() -> None:
    """Emit structured JSON logs to stdout (Docker captures stdout; no external sink)."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


class HealthResponse(BaseModel):
    """Liveness payload with real loaded-translation, verse, and cross-ref counts."""

    status: Literal["ok"] = "ok"
    translation_count: int = 0
    verse_count: int = 0
    cross_ref_count: int = 0
    book_count: int = 0


def _verify_and_cache(app: FastAPI) -> None:
    """Open the DB read-only, verify the schema, and cache counts/translations on state."""
    db_path: str = app.state.db_path
    try:
        conn = connect_readonly(db_path)
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"cannot open bible.db at {db_path!r} ({exc}); build it with `make build-db`."
        ) from exc
    try:
        try:
            translation_count = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
            verse_count = conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
            cross_ref_count = conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
            book_count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            loaded = {row[0] for row in conn.execute("SELECT id FROM translations")}
        except sqlite3.OperationalError as exc:
            raise RuntimeError(
                f"bible.db at {db_path!r} is missing expected tables ({exc}); "
                "rebuild with `make build-db`."
            ) from exc
    finally:
        conn.close()

    default = config.default_translation()
    if default not in loaded:
        raise RuntimeError(
            f"CONCORD_DEFAULT_TRANSLATION={default!r} is not loaded "
            f"(loaded: {sorted(loaded)}); set it to a loaded translation."
        )

    app.state.translations = loaded
    app.state.default_translation = default
    app.state.translation_count = translation_count
    app.state.verse_count = verse_count
    app.state.cross_ref_count = cross_ref_count
    app.state.book_count = book_count


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Verify the DB, cache state, and log one startup line (proves the core import too)."""
    _verify_and_cache(app)
    structlog.get_logger("bible_api").info(
        "concord.api.startup",
        api_version=__version__,
        core_version=bible_core.__version__,
        db_path=app.state.db_path,
        translations=app.state.translation_count,
        verses=app.state.verse_count,
        default_translation=app.state.default_translation,
        cors_origins=config.cors_origins(),
    )
    yield


@router.get("/healthz")
def healthz(request: Request) -> HealthResponse:
    state = request.app.state
    return HealthResponse(
        translation_count=state.translation_count,
        verse_count=state.verse_count,
        cross_ref_count=state.cross_ref_count,
        book_count=state.book_count,
    )


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Build the FastAPI application, pointed at ``db_path`` (default: config/env)."""
    _configure_logging()
    app = FastAPI(
        title="Concord",
        version=__version__,
        summary="A self-hosted, LAN-first, read-only Scripture API.",
        lifespan=lifespan,
    )
    app.state.db_path = str(db_path) if db_path is not None else config.db_path()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins(),
        # Read-only, LAN-trusted, no auth/cookies — so credentials stay off, which is
        # also what keeps the permissive "*" origin a safe default.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(router)
    app.include_router(v1_router)
    return app


app = create_app()
