"""A DB-free book resolver fixture for the parser unit tests."""

from __future__ import annotations

from bible_core.resolver import DictBookResolver

# A handful of real books (id, name, short aliases). from_books also registers each
# book's normalized name and id, so "Genesis", "1 John", "Song of Solomon" resolve too.
_BOOKS = [
    ("GEN", "Genesis", ["gen", "ge", "gn"]),
    ("JHN", "John", ["jhn", "jn", "joh"]),
    ("1JN", "1 John", ["1jn", "1joh", "1jo", "1j"]),
    ("1SA", "1 Samuel", ["1sa", "1sam", "1sm", "1s"]),
    ("2KI", "2 Kings", ["2ki", "2kgs", "2kin", "2k"]),
    ("JUD", "Jude", ["jud", "jd"]),
    ("JDG", "Judges", ["jdg", "judg", "jg"]),
    ("REV", "Revelation", ["rev", "re", "rv"]),
    ("SNG", "Song of Solomon", ["sng", "song", "sos", "ss"]),
]


def make_resolver() -> DictBookResolver:
    return DictBookResolver.from_books(_BOOKS)
