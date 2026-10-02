"""Build-time documents loader — a translation's documents (v8, ADR-0012).

A study Bible prints things tied to a whole book or to no verse: book introductions, front
matter, a reading plan, notes about the edition. Each is a **document** of its translation —
Markdown text under a slug — loaded into ``translation_documents`` (and the images its text
places into ``document_images``).

**Where.** ``<documents dir>/<file>.json``, one file per translation, scanned non-recursively.
The CLI scans ``data/private/documents/`` only: documents are user-supplied (a study Bible the
operator owns), dual-ignored like everything under ``data/private/``, so a clean build bakes
**zero** documents. A missing directory loads nothing — not an error.

**Input contract (per documents JSON file)**::

    {
      "translation": "EMB",                 # must match a loaded translation id
      "documents": [
        {
          "slug": "introduction-gen",       # [a-z0-9][a-z0-9-]{0,63}, unique per translation
          "kind": "book-introduction",      # front-matter | reading-plan | book-introduction
                                            #   | about
          "title": "...",                   # required, non-empty
          "book": "GEN",                    # book introductions only (an alias); one per book
          "ordinal": 1,                     # >= 1, unique per (translation, kind)
          "text": "## ...\\n\\n![...](asset:figure-gen.jpg)"   # Markdown, required
        }
      ]
    }

**Rules (each violation fails the build, naming the file and the document).** The fields
above; ``ref:`` link targets follow ADR-0011's grammar and name known books (as in notes); an
image is placed with ``![alt](asset:NAME)``, NAME an asset of the document's own translation —
``asset:`` serves images only, never a plain link. A document's images are read from its text
(in order of first use), never supplied, so the two can't disagree. Unknown keys are ignored.

Document ids are assigned deterministically (files in sorted-path order, documents in array
order), so the same inputs yield a byte-identical database. Pure stdlib (``json`` +
``sqlite3``) — ``bible-core`` stays web-free and ML-free.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .loader import LoaderError
from .normalize import normalize
from .notes import check_ref_links

# The document kinds, in the order a list shows them: front matter and a reading plan come
# before the books, as a study Bible prints them; notes about the edition come last. Mirrors
# the schema CHECK.
DOCUMENT_KINDS: tuple[str, ...] = ("front-matter", "reading-plan", "book-introduction", "about")
BOOK_INTRODUCTION = "book-introduction"

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")

# Every ``](asset:NAME)`` in the text; each must close an image's alt text (``![alt]``).
_ASSET_TARGET = re.compile(r"\]\(asset:([^)]*)\)")

# (id, translation_id, slug, kind, title, book_id, ordinal, text)
DocumentRow = tuple[int, str, str, str, str, str | None, int, str]
# (document_id, position, name)
DocumentImageRow = tuple[int, int, str]


@dataclass(frozen=True)
class DocumentsStats:
    """Summary of a completed documents load."""

    documents: int
    document_images: int


# --- JSON extraction helpers (validate + narrow types, with actionable errors) -------


def _get(obj: Any, key: str, ctx: str) -> Any:
    if not isinstance(obj, dict):
        raise LoaderError(f"{ctx}: expected a JSON object, got {type(obj).__name__}.")
    mapping = cast("dict[str, Any]", obj)
    if key not in mapping:
        raise LoaderError(f"{ctx}: missing required field {key!r}.")
    return mapping[key]


def _req_str(obj: Any, key: str, ctx: str) -> str:
    value = _get(obj, key, ctx)
    if not isinstance(value, str):
        raise LoaderError(f"{ctx}: field {key!r} must be a string, got {type(value).__name__}.")
    return value


def _req_text(obj: Any, key: str, ctx: str) -> str:
    """A required string field, non-empty after trimming (returned trimmed)."""
    value = _req_str(obj, key, ctx).strip()
    if not value:
        raise LoaderError(f"{ctx}: {key!r} is empty.")
    return value


def _req_int(obj: Any, key: str, ctx: str) -> int:
    value = _get(obj, key, ctx)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoaderError(f"{ctx}: field {key!r} must be an integer, got {type(value).__name__}.")
    return value


def _req_list(obj: Any, key: str, ctx: str) -> list[Any]:
    value = _get(obj, key, ctx)
    if not isinstance(value, list):
        raise LoaderError(f"{ctx}: field {key!r} must be a list, got {type(value).__name__}.")
    return cast("list[Any]", value)


def _opt_str(obj: dict[str, Any], key: str, ctx: str) -> str | None:
    if key not in obj or obj[key] is None:
        return None
    value = obj[key]
    if not isinstance(value, str):
        raise LoaderError(f"{ctx}: field {key!r} must be a string, got {type(value).__name__}.")
    return value


# --- parsing -------------------------------------------------------------------------


def image_names(text: str, assets: frozenset[str], translation_id: str, ctx: str) -> list[str]:
    """The asset names ``text`` places as images, in order of first use.

    Each ``asset:`` target must close an image's alt text and name one of ``assets``."""
    names: list[str] = []
    for match in _ASSET_TARGET.finditer(text):
        name = match.group(1)
        opening = _opening_bracket(text, match.start())
        if opening < 1 or text[opening - 1] != "!":
            raise LoaderError(
                f"{ctx}: asset:{name} is used as a link; an 'asset:' target places an image "
                "('![alt](asset:NAME)')."
            )
        if name not in assets:
            raise LoaderError(
                f"{ctx}: image asset:{name} names no asset of translation {translation_id!r}."
            )
        if name not in names:
            names.append(name)
    return names


def _opening_bracket(text: str, close: int) -> int:
    """Where the ``[`` that the ``]`` at ``close`` closes sits (-1 when there is none).

    Backslash-escaped brackets don't count; nested brackets balance, as CommonMark allows in
    link text."""
    depth = 0
    at = close - 1
    while at >= 0:
        char = text[at]
        escaped = at > 0 and text[at - 1] == "\\"
        if char == "]" and not escaped:
            depth += 1
        elif char == "[" and not escaped:
            if depth == 0:
                return at
            depth -= 1
        at -= 1
    return -1


def parse_documents_file(
    path: Path,
    next_id: int,
    translation_ids: frozenset[str],
    alias_to_book: dict[str, str],
    asset_names: Mapping[str, frozenset[str]],
) -> tuple[str, list[DocumentRow], list[DocumentImageRow]]:
    """Parse one documents JSON file: its translation, document rows and image rows.

    Document ids are assigned from ``next_id`` upward, in array order. The per-file rules are
    checked here; the rules across files (slugs, ordinals, one introduction per book) by
    ``load_documents``."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path.name}: invalid JSON ({exc}).") from exc

    translation_id = _req_str(raw, "translation", path.name)
    if translation_id not in translation_ids:
        known = ", ".join(sorted(translation_ids)) or "(none loaded)"
        raise LoaderError(
            f"{path.name}: documents reference translation {translation_id!r}, which is not a "
            f"loaded translation. Known translations: {known}."
        )

    book_ids = frozenset(alias_to_book.values())
    assets = asset_names.get(translation_id, frozenset[str]())
    rows: list[DocumentRow] = []
    images: list[DocumentImageRow] = []
    document_id = next_id
    for index, document in enumerate(_req_list(raw, "documents", path.name)):
        ctx = f"{path.name} documents[{index}]"
        slug = _req_str(document, "slug", ctx)
        if SLUG.fullmatch(slug) is None:
            raise LoaderError(
                f"{ctx}: slug {slug!r} is not lower-case letters, digits and '-' (starting "
                "with a letter or digit, at most 64 characters)."
            )
        kind = _req_str(document, "kind", ctx)
        if kind not in DOCUMENT_KINDS:
            raise LoaderError(
                f"{ctx}: unknown kind {kind!r} (expected one of {', '.join(DOCUMENT_KINDS)})."
            )
        title = _req_text(document, "title", ctx)
        book = _opt_str(cast("dict[str, Any]", document), "book", ctx)
        book_id: str | None = None
        if kind == BOOK_INTRODUCTION:
            if book is None:
                raise LoaderError(f"{ctx}: a book introduction needs its 'book'.")
            book_id = alias_to_book.get(normalize(book))
            if book_id is None:
                raise LoaderError(f"{ctx}: book {book!r} does not resolve to a known book.")
        elif book is not None:
            raise LoaderError(f"{ctx}: only a book introduction has a 'book' (this is {kind}).")
        ordinal = _req_int(document, "ordinal", ctx)
        if ordinal < 1:
            raise LoaderError(f"{ctx}: 'ordinal' must be >= 1.")
        text = _req_text(document, "text", ctx)
        check_ref_links(text, book_ids, ctx)
        names = image_names(text, assets, translation_id, ctx)

        rows.append((document_id, translation_id, slug, kind, title, book_id, ordinal, text))
        images.extend((document_id, position, name) for position, name in enumerate(names, 1))
        document_id += 1
    return translation_id, rows, images


# --- discovery + load ----------------------------------------------------------------


def discover_documents_files(documents_dirs: list[Path]) -> list[Path]:
    """Every ``*.json`` directly under each of ``documents_dirs``: the directories in order,
    files sorted by path within each."""
    files: list[Path] = []
    for documents_dir in documents_dirs:
        if documents_dir.is_dir():
            files.extend(sorted(documents_dir.glob("*.json"), key=lambda p: str(p)))
    return files


def _check_unique(path: Path, rows: list[DocumentRow], taken: dict[tuple[str, ...], str]) -> None:
    """A slug, a (kind, ordinal) and a book's introduction each occur once per translation."""
    for row in rows:
        _, translation_id, slug, kind, _, book_id, ordinal, _ = row
        where = f"{path.name} document {slug!r}"
        keys = {
            (translation_id, "slug", slug): f"{where}: translation {translation_id!r} already "
            "has a document with this slug",
            (translation_id, "ordinal", kind, str(ordinal)): f"{where}: translation "
            f"{translation_id!r} already has ordinal {ordinal} among its {kind!r} documents",
        }
        if book_id is not None:
            keys[(translation_id, "book", book_id)] = (
                f"{where}: translation {translation_id!r} already has an introduction to {book_id}"
            )
        for key, message in keys.items():
            if key in taken:
                raise LoaderError(f"{message} ({taken[key]}).")
            taken[key] = slug


def load_documents(
    conn: sqlite3.Connection,
    documents_dirs: list[Path],
    translation_ids: frozenset[str],
    alias_to_book: dict[str, str],
    asset_names: Mapping[str, frozenset[str]],
) -> DocumentsStats:
    """Ingest the documents JSON files under ``documents_dirs`` into ``translation_documents``
    and ``document_images``. ``asset_names`` holds each translation's loaded asset names, which
    a document's images must be among. A missing or empty directory loads nothing."""
    rows: list[DocumentRow] = []
    images: list[DocumentImageRow] = []
    taken: dict[tuple[str, ...], str] = {}
    next_id = 1
    for path in discover_documents_files(documents_dirs):
        _, file_rows, file_images = parse_documents_file(
            path, next_id, translation_ids, alias_to_book, asset_names
        )
        _check_unique(path, file_rows, taken)
        rows.extend(file_rows)
        images.extend(file_images)
        next_id += len(file_rows)

    conn.executemany(
        "INSERT INTO translation_documents "
        "(id, translation_id, slug, kind, title, book_id, ordinal, text) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.executemany(
        "INSERT INTO document_images (document_id, position, name) VALUES (?, ?, ?)", images
    )
    return DocumentsStats(documents=len(rows), document_images=len(images))
