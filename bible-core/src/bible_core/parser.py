"""Pure reference parser for the SPEC §5 grammar.

Turns strings like ``"John 3:16-18"`` into a structured :class:`Reference` (a normalized
list of :class:`Span`) plus a canonical echo string. Pure: the only external dependency
is an injected :class:`~bible_core.resolver.BookResolver`; no DB, no I/O, no globals.

The parser enforces only *grammar-level* invariants (positive integers, well-formed
ranges/lists). It does **not** bounds-check chapter/verse against real content —
``John 1:99999999`` parses fine; whether that verse exists is the HTTP layer's concern
(Slice 4 → 404). Ranges are never expanded, so huge ranges stay one cheap Span.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .resolver import BookResolver

# Unicode dashes users paste from word processors, all folded to ASCII '-'.
_DASHES = "‐‑‒–—―−"
_DASH_TABLE = str.maketrans(_DASHES, "-" * len(_DASHES))
_SPEC_CHARS = set("0123456789:,-")


class ParseError(Exception):
    """Raised when a reference string is not valid per the SPEC §5 grammar."""


class UnknownBookError(ParseError):
    """The grammar is well-formed but the book token resolves to no known book.

    A subclass of :class:`ParseError` (so existing ``except ParseError`` callers still
    catch it) that lets the HTTP layer distinguish "unparseable" (400) from "unknown
    book" (404) per SPEC §7.
    """


@dataclass(frozen=True)
class Span:
    """A contiguous selection within one book.

    ``start_verse``/``end_verse`` are both ``None`` for a whole-chapter selection
    (``Span(3, None, 3, None)`` = all of chapter 3; ``Span(3, None, 4, None)`` =
    chapters 3–4). Otherwise both are set: a single verse has equal bounds, a verse
    range shares a chapter, and a cross-chapter range spans two.
    """

    start_chapter: int
    start_verse: int | None
    end_chapter: int
    end_verse: int | None


@dataclass(frozen=True)
class Reference:
    """A parsed reference: one book, a normalized span list, and a canonical echo."""

    book_id: str
    book_name: str
    spans: tuple[Span, ...]
    echo: str


def parse_reference(text: str, resolver: BookResolver) -> Reference:
    """Parse ``text`` into a :class:`Reference`, or raise :class:`ParseError`."""
    raw = text.strip()
    if not raw:
        raise ParseError("empty reference")
    if ";" in raw:
        raise ParseError(
            "multiple references (';') are not supported; request one reference at a time"
        )

    book_token, spec = _split_book_and_spec(raw.translate(_DASH_TABLE))
    info = resolver.resolve(book_token)
    if info is None:
        raise UnknownBookError(f"unrecognised book {book_token!r}")

    spans = _parse_spec(spec, raw)
    return Reference(
        book_id=info.id,
        book_name=info.name,
        spans=spans,
        echo=_echo(info.name, spans),
    )


def _split_book_and_spec(text: str) -> tuple[str, str]:
    """Split into a book token and a chapter/verse spec.

    The spec is purely numeric + separators (no letters), so the book name ends at the
    last ASCII letter; everything after (minus leading book-trailing punctuation) is the
    spec. Handles ``1 John 3:16``, ``Song of Solomon 1:1``, and ``Jn. 3:16`` uniformly.
    """
    last_letter = -1
    for index, char in enumerate(text):
        if char.isascii() and char.isalpha():
            last_letter = index
    if last_letter == -1:
        raise ParseError(f"no book name found in {text!r}")

    book = text[: last_letter + 1].strip()
    spec = text[last_letter + 1 :].lstrip(" .'’\t")
    if not spec:
        raise ParseError(
            f"{text!r} is missing a chapter/verse — a reference needs at least a chapter number"
        )
    return book, spec


def _parse_spec(spec: str, raw: str) -> tuple[Span, ...]:
    spec = re.sub(r"\s+", "", spec).replace(".", ":")  # '.' and ':' are the same separator
    unexpected = [char for char in spec if char not in _SPEC_CHARS]
    if unexpected:
        raise ParseError(f"unexpected character {unexpected[0]!r} in reference {raw!r}")

    if "," in spec:
        return _parse_list(spec, raw)
    if "-" in spec:
        return _parse_range(spec, raw)
    if ":" in spec:
        chapter, verse = _split_cv(spec, raw)
        return (Span(chapter, verse, chapter, verse),)
    chapter = _parse_int(spec, "chapter", raw)
    return (Span(chapter, None, chapter, None),)


def _parse_range(spec: str, raw: str) -> tuple[Span, ...]:
    parts = spec.split("-")
    if len(parts) != 2:
        raise ParseError(f"malformed range {spec!r} in {raw!r}: expected exactly one '-'")
    left, right = parts
    if not left or not right:
        raise ParseError(f"range {spec!r} in {raw!r} is missing a bound")

    left_cv = ":" in left
    right_cv = ":" in right

    if not left_cv and not right_cv:  # chapter range, e.g. 3-4
        c1 = _parse_int(left, "chapter", raw)
        c2 = _parse_int(right, "chapter", raw)
        if c2 < c1:
            raise ParseError(f"descending chapter range {spec!r} in {raw!r}")
        return (Span(c1, None, c2, None),) if c1 != c2 else (Span(c1, None, c1, None),)

    if left_cv and not right_cv:  # same-chapter verse range, e.g. 3:16-18
        chapter, v1 = _split_cv(left, raw)
        v2 = _parse_int(right, "verse", raw)
        if v2 < v1:
            raise ParseError(f"descending verse range {spec!r} in {raw!r}")
        return (Span(chapter, v1, chapter, v2),) if v1 != v2 else (Span(chapter, v1, chapter, v1),)

    if not left_cv and right_cv:  # e.g. 3-4:2
        raise ParseError(
            f"ambiguous range {spec!r} in {raw!r}: a bare chapter on the left and "
            "chapter:verse on the right; write it as C:V-C:V"
        )

    # cross-chapter range, e.g. 3:16-4:2
    c1, v1 = _split_cv(left, raw)
    c2, v2 = _split_cv(right, raw)
    if (c2, v2) < (c1, v1):
        raise ParseError(f"descending range {spec!r} in {raw!r}")
    if c1 == c2:  # same chapter expressed cross-form → collapse
        return (Span(c1, v1, c1, v2),) if v1 != v2 else (Span(c1, v1, c1, v1),)
    return (Span(c1, v1, c2, v2),)


def _parse_list(spec: str, raw: str) -> tuple[Span, ...]:
    elements = spec.split(",")
    if any(element == "" for element in elements):
        raise ParseError(f"empty list element in {raw!r} (adjacent commas?)")

    first = elements[0]
    if ":" not in first:
        raise ParseError(
            f"a verse list must start with chapter:verse, e.g. 3:16,18 (got {first!r} in {raw!r})"
        )
    chapter, first_verse = _split_cv(first, raw)

    verses = [first_verse]
    for element in elements[1:]:
        if ":" in element or "-" in element:
            raise ParseError(
                f"verse-list elements after the first must be bare verse numbers "
                f"(got {element!r} in {raw!r}); cross-chapter lists and ranges in lists "
                "are not supported in v1"
            )
        verses.append(_parse_int(element, "verse", raw))

    return tuple(Span(chapter, verse, chapter, verse) for verse in sorted(set(verses)))


def _split_cv(token: str, raw: str) -> tuple[int, int]:
    parts = token.split(":")
    if len(parts) != 2:
        raise ParseError(f"{token!r} is not a valid chapter:verse in {raw!r}")
    return _parse_int(parts[0], "chapter", raw), _parse_int(parts[1], "verse", raw)


def _parse_int(token: str, label: str, raw: str) -> int:
    if not token.isdigit():
        raise ParseError(f"expected a {label} number but got {token!r} in {raw!r}")
    value = int(token)
    if value < 1:
        raise ParseError(f"{label} number must be positive (got {value}) in {raw!r}")
    return value


def _echo(book_name: str, spans: tuple[Span, ...]) -> str:
    if len(spans) == 1:
        return f"{book_name} {_echo_span(spans[0])}"
    # verse list: every span is a same-chapter point-span (by construction)
    chapter = spans[0].start_chapter
    verses = ",".join(str(span.start_verse) for span in spans)
    return f"{book_name} {chapter}:{verses}"


def _echo_span(span: Span) -> str:
    if span.start_verse is None:  # whole-chapter selection (end_verse also None)
        if span.start_chapter == span.end_chapter:
            return str(span.start_chapter)
        return f"{span.start_chapter}-{span.end_chapter}"
    if span.start_chapter == span.end_chapter:
        if span.start_verse == span.end_verse:
            return f"{span.start_chapter}:{span.start_verse}"
        return f"{span.start_chapter}:{span.start_verse}-{span.end_verse}"
    return f"{span.start_chapter}:{span.start_verse}-{span.end_chapter}:{span.end_verse}"
