"""A malformed canonical-books source fails loudly with an actionable error."""

from __future__ import annotations

import pytest
from bible_core.seed import (
    BookSeed,
    SeedValidationError,
    parse_canonical_books,
    validate_books,
)


def _valid_books(n: int = 66) -> list[BookSeed]:
    """Synthetic books that pass every validation, for targeted single-defect tests."""
    books: list[BookSeed] = []
    for i in range(1, n + 1):
        book_id = f"B{i:02d}"  # 3-char, uppercase-or-digit
        name = f"book{i}"
        books.append(
            BookSeed(
                id=book_id,
                name=name,
                testament="OT" if i <= 39 else "NT",
                canonical_order=i,
                aliases=(name, book_id.lower()),
            )
        )
    return books


def test_valid_synthetic_books_pass() -> None:
    validate_books(_valid_books())  # sanity: the fixture itself is valid


def test_wrong_book_count() -> None:
    with pytest.raises(SeedValidationError, match="66 books"):
        validate_books(_valid_books(65))


def test_canonical_order_gap() -> None:
    books = _valid_books()
    books[0] = BookSeed("B01", "book1", "OT", 99, ("book1", "b01"))
    with pytest.raises(SeedValidationError, match="canonical_order"):
        validate_books(books)


def test_malformed_usfm_code() -> None:
    books = _valid_books()
    books[0] = BookSeed("XX", "book1", "OT", 1, ("book1", "xx"))
    with pytest.raises(SeedValidationError, match="USFM"):
        validate_books(books)


def test_duplicate_alias_across_books() -> None:
    books = _valid_books()
    books[0] = BookSeed("B01", "book1", "OT", 1, ("book1", "b01", "dup"))
    books[1] = BookSeed("B02", "book2", "OT", 2, ("book2", "b02", "dup"))
    with pytest.raises(SeedValidationError, match="maps to both"):
        validate_books(books)


def test_non_normalized_alias() -> None:
    books = _valid_books()
    books[0] = BookSeed("B01", "book1", "OT", 1, ("book1", "b01", "BadAlias"))
    with pytest.raises(SeedValidationError, match="normal form"):
        validate_books(books)


def test_name_not_in_aliases() -> None:
    books = _valid_books()
    books[0] = BookSeed("B01", "Genesis", "OT", 1, ("b01",))
    with pytest.raises(SeedValidationError, match="not among"):
        validate_books(books)


# --- parse-level failures (structural) ---------------------------------------

_HEADER = (
    "## Old Testament\n"
    "| # | USFM | Name | Testament | Aliases (normalized) |\n"
    "|---|---|---|---|---|\n"
)


def test_testament_mismatched_to_section() -> None:
    text = _HEADER + "| 1 | GEN | Genesis | NT | gen |\n"
    with pytest.raises(SeedValidationError, match="section"):
        parse_canonical_books(text)


def test_wrong_column_count() -> None:
    text = "## Old Testament\n| # | USFM | Name |\n|---|---|---|\n| 1 | GEN | Genesis |\n"
    with pytest.raises(SeedValidationError, match="5 columns"):
        parse_canonical_books(text)


def test_non_integer_order() -> None:
    text = _HEADER + "| X | GEN | Genesis | OT | gen |\n"
    with pytest.raises(SeedValidationError, match="canonical order"):
        parse_canonical_books(text)
