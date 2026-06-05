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


def _envelope(code: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


def _error_response(
    status: int, code: str, message: str, detail: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status, content=_envelope(code, message, detail))


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
    app.add_exception_handler(RequestValidationError, _handle_validation)
