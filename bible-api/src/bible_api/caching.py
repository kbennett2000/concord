"""ETag + Cache-Control for the immutable verse data (SPEC §7).

Verses never change, so every successful response carries a strong, body-derived ETag
and a one-year immutable Cache-Control, and honors ``If-None-Match`` with a 304. The
ETag is hashed from the exact bytes sent, so it is correct by construction.
"""

from __future__ import annotations

import hashlib

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel

from .errors import CACHE_CONTROL


def _etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


def cached_json_response(model: BaseModel, request: Request) -> Response:
    """Serialize ``model`` to JSON with a strong ETag; return 304 on an If-None-Match hit."""
    # by_alias serializes fields with a serialization alias (e.g. cross-refs' "from");
    # a no-op for every model without aliases.
    body = model.model_dump_json(by_alias=True).encode("utf-8")
    etag = _etag(body)
    # Vary: Origin marks the response as origin-dependent so a cache entry created by a
    # no-Origin navigation (no Access-Control-Allow-Origin) is not replayed to a later
    # cross-origin fetch, whose CORS check would then fail. See docs/SECURITY.md.
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL, "Vary": "Origin"}

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and etag in {tag.strip() for tag in if_none_match.split(",")}:
        return Response(status_code=304, headers=headers)

    return Response(content=body, media_type="application/json", headers=headers)


def no_store_json_response(model: BaseModel) -> Response:
    """Serialize ``model`` to JSON with ``Cache-Control: no-store`` and **no** ETag.

    For /random, whose whole point is a fresh result each call — the immutable-ETag
    pattern would let clients keep replaying one "random" verse, so it must not apply.
    """
    body = model.model_dump_json(by_alias=True).encode("utf-8")
    return Response(
        content=body, media_type="application/json", headers={"Cache-Control": "no-store"}
    )
