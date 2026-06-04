"""FastAPI application factory and the ``/healthz`` endpoint.

Slice 0 proves the wiring only: bible-api imports bible-core, FastAPI boots, CORS is
configured from the environment, structlog emits JSON to stdout, and ``/healthz``
answers 200. No feature endpoints yet — those arrive from Slice 4 onward.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal

import bible_core
import structlog
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__, config

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
    """Liveness payload. Counts are placeholders until the DB lands (Slice 7)."""

    status: Literal["ok"] = "ok"
    translation_count: int = 0
    verse_count: int = 0


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Log a single startup line — and prove the cross-package import works."""
    log = structlog.get_logger("bible_api")
    log.info(
        "concord.api.startup",
        api_version=__version__,
        core_version=bible_core.__version__,
        cors_origins=config.cors_origins(),
    )
    yield


@router.get("/healthz")
def healthz() -> HealthResponse:
    return HealthResponse()


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    _configure_logging()
    app = FastAPI(
        title="Concord",
        version=__version__,
        summary="A self-hosted, LAN-first, read-only Scripture API.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins(),
        # Read-only, LAN-trusted, no auth/cookies — so credentials stay off, which is
        # also what keeps the permissive "*" origin a safe default.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
