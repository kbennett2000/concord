"""End-to-end seed against the real packaged canonical-books.md."""

from __future__ import annotations

import sqlite3

import pytest
from bible_core.normalize import normalize
from bible_core.schema import create_schema
from bible_core.seed import load_canonical_books_text, parse_canonical_books, seed_books


@pytest.fixture
def seeded() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    seed_books(conn)
    return conn


def _resolve(conn: sqlite3.Connection, alias: str) -> str | None:
    row = conn.execute("SELECT book_id FROM book_aliases WHERE alias = ?", (alias,)).fetchone()
    return None if row is None else row[0]


def test_exactly_66_books(seeded: sqlite3.Connection) -> None:
    assert seeded.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 66


def test_canonical_order_is_1_to_66(seeded: sqlite3.Connection) -> None:
    orders = [r[0] for r in seeded.execute("SELECT canonical_order FROM books ORDER BY 1")]
    assert orders == list(range(1, 67))


def test_chapter_count_is_null_after_seed(seeded: sqlite3.Connection) -> None:
    # The loader (Slice 2) computes this from verse data; the seed leaves it NULL.
    nulls = seeded.execute("SELECT COUNT(*) FROM books WHERE chapter_count IS NULL").fetchone()[0]
    assert nulls == 66


@pytest.mark.parametrize(
    ("alias", "book_id"),
    [
        # the two deliberate disambiguation choices
        ("jud", "JUD"),  # Jude, never Judges
        ("jdg", "JDG"),  # Judges, never Jude
        # numbered-book digit prefixes
        ("1ki", "1KI"),
        ("2ki", "2KI"),
        ("1sam", "1SA"),
        # multi-word name, normalized
        ("songofsolomon", "SNG"),
        ("songofsongs", "SNG"),
        # plain codes / names
        ("gen", "GEN"),
        ("revelation", "REV"),
    ],
)
def test_alias_resolution(seeded: sqlite3.Connection, alias: str, book_id: str) -> None:
    assert _resolve(seeded, alias) == book_id


def test_jud_never_resolves_to_judges(seeded: sqlite3.Connection) -> None:
    assert _resolve(seeded, "jud") != "JDG"


def test_every_name_and_code_roundtrips() -> None:
    books = parse_canonical_books(load_canonical_books_text())
    for book in books:
        assert normalize(book.name) in book.aliases
        assert book.id.lower() in book.aliases


def test_all_stored_aliases_are_normalized() -> None:
    books = parse_canonical_books(load_canonical_books_text())
    for book in books:
        for alias in book.aliases:
            assert normalize(alias) == alias
