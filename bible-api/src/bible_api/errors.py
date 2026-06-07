"""The consistent error envelope and its exception handlers.

Every error response — from the parser, the query layer, or FastAPI's own validation —
is shaped as ``{"error": {"code", "message", "detail"}}`` (CLAUDE.md / SPEC §7), so
clients get one uniform error contract.
"""

from __future__ import annotations

from typing import Any, cast

from bible_core.parser import ParseError, UnknownBookError
from bible_core.queries import SearchQueryError
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

CACHE_CONTROL = "public, max-age=31536000, immutable"


class UnknownTranslationError(Exception):
    """A requested ``?translations=`` id is not loaded."""

    def __init__(self, translation: str, available: list[str]) -> None:
        super().__init__(f"unknown translation {translation!r}")
        self.translation = translation
        self.available = available

    @property
    def detail(self) -> dict[str, Any]:
        return {"translation": self.translation, "available": sorted(self.available)}


class NoVersesFoundError(Exception):
    """A well-formed reference matched no verse in any requested translation."""


class BookFilterError(Exception):
    """A ``?book=`` *filter* value (a query param) did not resolve to a known book.

    Maps to 400 — distinct from ``/verses`` where the book is a path resource (404).
    """


class NoMatchError(Exception):
    """A /random request's filters (book/testament) matched no verse."""


class SemanticUnavailableError(Exception):
    """Semantic search was requested but is disabled / not primed on this instance."""


class SemanticBusyError(Exception):
    """Semantic search is at its concurrency cap; the request is shed (ADR-0001)."""


class SemanticTimeoutError(Exception):
    """A single semantic inference exceeded the server-side wall-clock deadline (ADR-0002)."""


class UnknownPlaceError(Exception):
    """A requested place id (a path resource) is not in the places table → 404."""

    def __init__(self, place_id: str) -> None:
        super().__init__(f"unknown place {place_id!r}")
        self.place_id = place_id

    @property
    def detail(self) -> dict[str, Any]:
        return {"place_id": self.place_id}


class PlaceFilterError(Exception):
    """A ``?type=``/``?status=`` *filter* value did not match a known value.

    Maps to 400 (a query-param filter), distinct from the 404 place-id path resource.
    Carries its own ``code`` so type and status filters report distinctly.
    """

    def __init__(self, code: str, message: str, detail: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail


def _envelope(code: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


def _error_response(
    status: int,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status, content=_envelope(code, message, detail), headers=headers
    )


async def _handle_unknown_book(_request: Request, exc: Exception) -> Response:
    return _error_response(404, "unknown_book", str(exc))


async def _handle_parse_error(_request: Request, exc: Exception) -> Response:
    return _error_response(400, "unparseable_reference", str(exc))


async def _handle_unknown_translation(_request: Request, exc: Exception) -> Response:
    detail = cast(UnknownTranslationError, exc).detail
    return _error_response(404, "unknown_translation", str(exc), detail)


async def _handle_no_verses(_request: Request, exc: Exception) -> Response:
    return _error_response(404, "no_verses_found", str(exc))


async def _handle_validation(_request: Request, exc: Exception) -> Response:
    errors = cast(RequestValidationError, exc).errors()
    detail = {"errors": jsonable_encoder(errors)}
    return _error_response(422, "invalid_parameter", "Invalid request parameters.", detail)


async def _handle_book_filter(_request: Request, exc: Exception) -> Response:
    return _error_response(400, "unknown_book", str(exc))


async def _handle_no_match(_request: Request, exc: Exception) -> Response:
    return _error_response(404, "no_match", str(exc))


async def _handle_search_query(_request: Request, exc: Exception) -> Response:
    return _error_response(
        400, "invalid_search_query", "Malformed search query.", {"fts5_error": str(exc)}
    )


async def _handle_semantic_unavailable(_request: Request, exc: Exception) -> Response:
    return _error_response(503, "semantic_unavailable", str(exc))


async def _handle_semantic_busy(_request: Request, exc: Exception) -> Response:
    # 503 (global capacity, not a per-client quota) + Retry-After (ADR-0001).
    return _error_response(503, "semantic_busy", str(exc), headers={"Retry-After": "1"})


async def _handle_semantic_timeout(_request: Request, exc: Exception) -> Response:
    # 503 (not 504): Concord is the origin doing its own compute, not a gateway awaiting an
    # upstream, and a deadline breach almost always means the box is genuinely overloaded — the
    # same "retry shortly" condition as semantic_busy, so clients back off uniformly. A distinct
    # code keeps "ran too long" separable from "shed before running" in logs (ADR-0002).
    return _error_response(503, "semantic_timeout", str(exc), headers={"Retry-After": "1"})


async def _handle_unknown_place(_request: Request, exc: Exception) -> Response:
    return _error_response(404, "unknown_place", str(exc), cast(UnknownPlaceError, exc).detail)


async def _handle_place_filter(_request: Request, exc: Exception) -> Response:
    place_exc = cast(PlaceFilterError, exc)
    return _error_response(400, place_exc.code, str(exc), place_exc.detail)


def register_error_handlers(app: FastAPI) -> None:
    """Map domain + validation exceptions to the envelope.

    ``UnknownBookError`` (a ``ParseError`` subclass) is registered separately so it maps
    to 404 while plain ``ParseError`` maps to 400 — Starlette dispatches by the most
    specific class in the exception's MRO.
    """
    app.add_exception_handler(UnknownBookError, _handle_unknown_book)
    app.add_exception_handler(ParseError, _handle_parse_error)
    app.add_exception_handler(UnknownTranslationError, _handle_unknown_translation)
    app.add_exception_handler(NoVersesFoundError, _handle_no_verses)
    app.add_exception_handler(BookFilterError, _handle_book_filter)
    app.add_exception_handler(NoMatchError, _handle_no_match)
    app.add_exception_handler(SearchQueryError, _handle_search_query)
    app.add_exception_handler(SemanticUnavailableError, _handle_semantic_unavailable)
    app.add_exception_handler(SemanticBusyError, _handle_semantic_busy)
    app.add_exception_handler(SemanticTimeoutError, _handle_semantic_timeout)
    app.add_exception_handler(UnknownPlaceError, _handle_unknown_place)
    app.add_exception_handler(PlaceFilterError, _handle_place_filter)
    app.add_exception_handler(RequestValidationError, _handle_validation)
