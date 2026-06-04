"""Seed ``books`` and ``book_aliases`` from ``canonical-books.md``.

``canonical-books.md`` is the authoritative source of reference data — this module
*parses* it (it never retypes the data) and validates the result against that file's own
"Review checklist" before inserting. A malformed source fails loudly with an actionable
message and writes nothing.

The file is shipped as package data (read via ``importlib.resources``) so ``bible-core``
stays self-contained when imported in-process; ``docs/canonical-books.md`` remains the
human source of truth, kept byte-identical by a drift-guard test.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .normalize import normalize

EXPECTED_BOOK_COUNT = 66
_SECTIONS = {"## Old Testament": "OT", "## New Testament": "NT"}


class SeedValidationError(Exception):
    """Raised when ``canonical-books.md`` does not satisfy the seed contract."""


@dataclass(frozen=True)
class BookSeed:
    """One parsed book row plus its aliases."""

    id: str
    name: str
    testament: str
    canonical_order: int
    aliases: tuple[str, ...]


def load_canonical_books_text(source: Path | None = None) -> str:
    """Return the raw markdown — the packaged copy by default, or an override path."""
    if source is not None:
        return source.read_text(encoding="utf-8")
    return files("bible_core").joinpath("data/canonical-books.md").read_text(encoding="utf-8")


def parse_canonical_books(text: str) -> list[BookSeed]:
    """Parse the OT and NT markdown tables into ``BookSeed`` rows.

    Anchors on the ``## Old Testament`` / ``## New Testament`` headings and reads the
    pipe-table under each, skipping the header and separator rows. Raises
    ``SeedValidationError`` on a structurally malformed row.
    """
    books: list[BookSeed] = []
    testament: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped in _SECTIONS:
            testament = _SECTIONS[stripped]
            continue
        if stripped.startswith("## "):  # any other heading ends the current section
            testament = None
            continue
        if testament is None or not stripped.startswith("|"):
            continue
        if "---" in stripped or "USFM" in stripped:  # separator / header row
            continue
        books.append(_parse_row(stripped, testament))

    return books


def _parse_row(line: str, testament: str) -> BookSeed:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) != 5:
        raise SeedValidationError(f"Expected 5 columns in book row, found {len(cells)}: {line!r}")
    order_text, usfm, name, testament_cell, alias_cell = cells
    try:
        canonical_order = int(order_text)
    except ValueError as exc:
        raise SeedValidationError(
            f"Non-integer canonical order {order_text!r} in row: {line!r}"
        ) from exc
    if testament_cell != testament:
        raise SeedValidationError(
            f"Book {usfm!r} is under the {testament} section but its row says {testament_cell!r}."
        )
    aliases = tuple(alias.strip() for alias in alias_cell.split(",") if alias.strip())
    return BookSeed(
        id=usfm,
        name=name,
        testament=testament,
        canonical_order=canonical_order,
        aliases=aliases,
    )


def validate_books(books: list[BookSeed]) -> None:
    """Validate parsed books against the ``canonical-books.md`` Review checklist.

    Raises ``SeedValidationError`` (never a bare stack trace) on the first failure.
    """
    if len(books) != EXPECTED_BOOK_COUNT:
        raise SeedValidationError(f"Expected {EXPECTED_BOOK_COUNT} books, parsed {len(books)}.")

    orders = sorted(book.canonical_order for book in books)
    if orders != list(range(1, EXPECTED_BOOK_COUNT + 1)):
        raise SeedValidationError(
            f"canonical_order must be exactly 1..66 with no gaps or duplicates; got {orders}."
        )

    for book in books:
        if len(book.id) != 3 or not book.id.isalnum() or not book.id.isupper():
            raise SeedValidationError(
                f"Invalid USFM code {book.id!r}: expected a 3-character uppercase code."
            )
        if book.testament not in {"OT", "NT"}:
            raise SeedValidationError(
                f"Book {book.id!r} has testament {book.testament!r}; the v1 seed only "
                "contains OT and NT books."
            )

    alias_to_book: dict[str, str] = {}
    for book in books:
        for alias in book.aliases:
            if alias in alias_to_book and alias_to_book[alias] != book.id:
                raise SeedValidationError(
                    f"Alias {alias!r} maps to both {alias_to_book[alias]!r} and "
                    f"{book.id!r}; aliases must be unique."
                )
            if alias in alias_to_book:
                raise SeedValidationError(f"Alias {alias!r} is duplicated for book {book.id!r}.")
            if normalize(alias) != alias:
                raise SeedValidationError(
                    f"Alias {alias!r} (book {book.id!r}) is not in normal form; "
                    f"normalize() yields {normalize(alias)!r}."
                )
            alias_to_book[alias] = book.id

    for book in books:
        normalized_name = normalize(book.name)
        if normalized_name not in book.aliases:
            raise SeedValidationError(
                f"Book {book.id!r}: normalized name {normalized_name!r} is not among "
                f"its aliases {book.aliases}."
            )
        if book.id.lower() not in book.aliases:
            raise SeedValidationError(
                f"Book {book.id!r}: lowercased USFM code {book.id.lower()!r} is not "
                f"among its aliases {book.aliases}."
            )


def seed_books(conn: sqlite3.Connection, source: Path | None = None) -> None:
    """Populate ``books`` and ``book_aliases`` from ``canonical-books.md``.

    Parse → validate fully → insert atomically. If validation fails nothing is written.
    ``chapter_count`` is left ``NULL``; the Slice 2 loader computes it from verse data.
    """
    books = parse_canonical_books(load_canonical_books_text(source))
    validate_books(books)

    book_rows = [(book.id, book.name, book.testament, book.canonical_order, None) for book in books]
    alias_rows = [(alias, book.id) for book in books for alias in book.aliases]

    with conn:  # single transaction: all rows land, or none do
        conn.executemany(
            "INSERT INTO books (id, name, testament, canonical_order, chapter_count) "
            "VALUES (?, ?, ?, ?, ?)",
            book_rows,
        )
        conn.executemany(
            "INSERT INTO book_aliases (alias, book_id) VALUES (?, ?)",
            alias_rows,
        )
