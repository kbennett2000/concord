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
import threading
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import bible_core
import structlog
from bible_core.db import connect_readonly
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import __version__, config
from .errors import register_error_handlers
from .routers import router as v1_router

router = APIRouter()

# Vendored Swagger UI / ReDoc assets, served from /static so /docs works fully offline.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_SWAGGER_FAVICON = "/static/swagger-ui/favicon-32x32.png"


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


class SemanticHealth(BaseModel):
    """Semantic-search readiness: the embedded translation, vector count, model, and dim."""

    enabled: bool
    translation: str | None = None
    embedding_count: int | None = None
    model: str | None = None
    dim: int | None = None


class HealthResponse(BaseModel):
    """Liveness payload with real loaded-translation, verse, and cross-ref counts."""

    status: Literal["ok"] = "ok"
    translation_count: int = 0
    verse_count: int = 0
    cross_ref_count: int = 0
    book_count: int = 0
    place_count: int = 0
    semantic: SemanticHealth | None = None


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
            place_count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
            loaded = {row[0] for row in conn.execute("SELECT id FROM translations")}
            book_names = {row[0]: row[1] for row in conn.execute("SELECT id, name FROM books")}
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
    app.state.place_count = place_count
    app.state.book_names = book_names


def _prime_semantic(app: FastAPI) -> None:
    """Load the embedding store (running the model-vs-vectors guard) and warm the model.

    An unusable store or a model/vectors mismatch raises ``RuntimeError`` → the app refuses
    to start, rather than failing on the first query. Warming the model with one forward
    pass means the first real query doesn't pay the one-time ONNX session init (~3 s).
    """
    from bible_semantic.model import embed_query
    from bible_semantic.store import StoreError, load_store

    try:
        store = load_store(app.state.embeddings_path)
    except StoreError as exc:
        raise RuntimeError(
            f"semantic search is enabled but the embeddings store is unusable: {exc}"
        ) from exc
    if store.meta.translation not in app.state.translations:
        raise RuntimeError(
            f"embedded translation {store.meta.translation!r} is not loaded in bible.db "
            f"(loaded: {sorted(app.state.translations)}); semantic results can't be hydrated."
        )
    embed_query("warm")  # one forward pass so the first real query is fast
    app.state.semantic_store = store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Verify the DB, cache state, optionally prime semantic search, and log one line."""
    _verify_and_cache(app)
    if app.state.semantic_enabled:
        _prime_semantic(app)
    store = app.state.semantic_store
    structlog.get_logger("bible_api").info(
        "concord.api.startup",
        api_version=__version__,
        core_version=bible_core.__version__,
        db_path=app.state.db_path,
        translations=app.state.translation_count,
        verses=app.state.verse_count,
        default_translation=app.state.default_translation,
        semantic=None
        if store is None
        else {"translation": store.meta.translation, "count": len(store.refs)},
        cors_origins=config.cors_origins(),
    )
    try:
        yield
    finally:
        executor = app.state.semantic_executor
        if executor is not None:
            # wait=False so a still-running (timed-out) inference can't block shutdown;
            # cancel_futures drops only not-yet-started work — a running pass can't be cancelled.
            executor.shutdown(wait=False, cancel_futures=True)


@router.get("/docs", include_in_schema=False)
def swagger_ui_html(request: Request) -> HTMLResponse:
    app = request.app
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url=_SWAGGER_FAVICON,
    )


@router.get("/docs/oauth2-redirect", include_in_schema=False)
def swagger_ui_redirect() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()


@router.get("/redoc", include_in_schema=False)
def redoc_html(request: Request) -> HTMLResponse:
    app = request.app
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — ReDoc",
        redoc_js_url="/static/redoc/redoc.standalone.js",
        redoc_favicon_url=_SWAGGER_FAVICON,
        with_google_fonts=False,  # ReDoc otherwise pulls Montserrat/Roboto from a CDN
    )


@router.get("/healthz")
def healthz(request: Request) -> HealthResponse:
    state = request.app.state
    store = state.semantic_store
    semantic = (
        SemanticHealth(
            enabled=True,
            translation=store.meta.translation,
            embedding_count=len(store.refs),
            model=store.meta.model,
            dim=store.meta.dim,
        )
        if store is not None
        else SemanticHealth(enabled=False)
    )
    return HealthResponse(
        translation_count=state.translation_count,
        verse_count=state.verse_count,
        cross_ref_count=state.cross_ref_count,
        book_count=state.book_count,
        place_count=state.place_count,
        semantic=semantic,
    )


class SecurityHeadersMiddleware:
    """Set ``X-Content-Type-Options: nosniff`` on every response.

    For a JSON API plus vendored offline docs, nosniff is the one security header that is
    unambiguously appropriate: it stops content-type sniffing without constraining anything,
    and the vendored Swagger UI / ReDoc assets are served with correct content types so it
    can't break them. No CSP — it would risk the offline docs and buys little for a
    read-only, LAN-trusted service (see docs/SECURITY.md). Pure ASGI so it adds the header
    even to error and static-file responses without buffering them.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).setdefault("X-Content-Type-Options", "nosniff")
            await send(message)

        await self.app(scope, receive, send_with_headers)


def create_app(
    db_path: str | Path | None = None,
    *,
    enable_semantic: bool | None = None,
    embeddings_path: str | Path | None = None,
    semantic_max_concurrency: int | None = None,
    semantic_timeout_s: float | None = None,
) -> FastAPI:
    """Build the FastAPI application, pointed at ``db_path`` (default: config/env).

    ``enable_semantic`` overrides ``CONCORD_SEMANTIC_SEARCH`` (the fast test suite passes
    ``False`` to skip the heavy model load). ``embeddings_path`` overrides where the vector
    store is read from (default: the store's own ``CONCORD_EMBEDDINGS_PATH`` resolution).
    ``semantic_max_concurrency`` overrides ``CONCORD_SEMANTIC_MAX_CONCURRENCY`` (the
    semantic-search concurrency cap; ADR-0001) and ``semantic_timeout_s`` overrides
    ``CONCORD_SEMANTIC_TIMEOUT_S`` (the per-inference wall-clock deadline; ADR-0002) — both
    per-app seams for tests.
    """
    _configure_logging()
    app = FastAPI(
        title="Concord",
        version=__version__,
        summary="A self-hosted, LAN-first, read-only Scripture API.",
        lifespan=lifespan,
        # Disable the CDN-backed defaults; we serve Swagger UI / ReDoc from vendored assets
        # (see the /docs and /redoc routes) so interactive docs work fully offline.
        docs_url=None,
        redoc_url=None,
    )
    app.state.db_path = str(db_path) if db_path is not None else config.db_path()
    app.state.semantic_enabled = (
        config.semantic_enabled() if enable_semantic is None else enable_semantic
    )
    app.state.embeddings_path = Path(embeddings_path) if embeddings_path is not None else None
    app.state.semantic_store = None
    # Semantic-search concurrency cap (ADR-0001): a bounded semaphore sheds excess inferences
    # with 503 + Retry-After. None = no cap (cap <= 0). Wraps only the inference in the handler.
    cap = (
        config.semantic_max_concurrency()
        if semantic_max_concurrency is None
        else semantic_max_concurrency
    )
    app.state.semantic_max_concurrency = cap
    app.state.semantic_semaphore = threading.BoundedSemaphore(cap) if cap > 0 else None
    # Per-inference wall-clock deadline (ADR-0002): run the inference in a small executor and
    # give up waiting after `timeout` seconds (503 + Retry-After). The timed-out worker keeps
    # running and holds its permit until it finishes, so the cap stays coupled to real CPU
    # exactly as ADR-0001 requires. Only meaningful with a cap on AND a positive timeout;
    # max_workers is pinned to the cap (acquire-before-submit bounds in-flight workers to it).
    timeout = config.semantic_timeout_s() if semantic_timeout_s is None else semantic_timeout_s
    app.state.semantic_timeout_s = timeout
    app.state.semantic_executor = (
        ThreadPoolExecutor(max_workers=cap, thread_name_prefix="semantic")
        if app.state.semantic_semaphore is not None and timeout > 0
        else None
    )
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    app.add_middleware(SecurityHeadersMiddleware)
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
