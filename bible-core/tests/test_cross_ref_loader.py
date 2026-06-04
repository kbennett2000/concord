"""Cross-reference load: row counts, target handling, idempotency, and validation."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import LoaderError, build_database
from loaderkit import book, chapter, translation, verse, write_translation

HEADER = "From Verse\tTo Verse\tVotes\t#www.openbible.info CC-BY\n"

# A small, valid fixture exercising single, same-chapter range, cross-chapter (clamped),
# and cross-book (clamped) targets.
GOOD_ROWS = [
    "Gen.1.1\tJohn.1.1\t40",
    "Gen.1.1\tPs.148.4-Ps.148.5\t30",  # same-chapter range
    "Gen.1.2\tPs.148.5-Ps.149.1\t20",  # cross-chapter range → clamp
    "Gen.1.3\tMal.4.6-Matt.1.1\t10",  # cross-book range → clamp
]


def _corpus(tmp_path: Path) -> Path:
    """One tiny translation so the build has verses; cross-refs are what we test."""
    tdir = tmp_path / "translations"
    payload = translation(
        "KJVX",
        [book("Gen", 1, [chapter(1, [verse(1, "x"), verse(2, "y"), verse(3, "z")])])],
    )
    write_translation(tdir, payload)
    return tdir


def _xref_dir(tmp_path: Path, rows: list[str], *, name: str = "xrefs.txt") -> Path:
    xdir = tmp_path / "xrefs"
    xdir.mkdir(parents=True, exist_ok=True)
    (xdir / name).write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return xdir


def test_row_count_and_target_shapes(tmp_path: Path) -> None:
    db = tmp_path / "bible.db"
    stats = build_database(db, [_corpus(tmp_path)], [_xref_dir(tmp_path, GOOD_ROWS)])
    assert stats.cross_references == 4
    assert stats.cross_refs_clamped == 2  # the two boundary-crossing ranges

    conn = sqlite3.connect(db)
    # single verse target: to_verse_end is NULL
    row = conn.execute(
        "SELECT to_book_id, to_chapter, to_verse_start, to_verse_end FROM cross_references "
        "WHERE from_book_id='GEN' AND from_verse=1 AND to_book_id='JHN'"
    ).fetchone()
    assert row == ("JHN", 1, 1, None)
    # same-chapter range target: to_verse_end set
    row = conn.execute(
        "SELECT to_chapter, to_verse_start, to_verse_end FROM cross_references "
        "WHERE from_verse=1 AND to_book_id='PSA'"
    ).fetchone()
    assert row == (148, 4, 5)
    # clamped cross-chapter target: keeps start, to_verse_end NULL
    row = conn.execute(
        "SELECT to_book_id, to_chapter, to_verse_start, to_verse_end FROM cross_references "
        "WHERE from_verse=2"
    ).fetchone()
    assert row == ("PSA", 148, 5, None)


def test_build_with_cross_refs_is_idempotent(tmp_path: Path) -> None:
    tdir, xdir = _corpus(tmp_path), _xref_dir(tmp_path, GOOD_ROWS)
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    build_database(a, [tdir], [xdir])
    build_database(b, [tdir], [xdir])
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        (["Gen.1.1\tJohn.1.1"], "3 tab-separated columns"),  # missing votes column
        (["Zzz.1.1\tJohn.1.1\t5"], "does not resolve"),  # unknown book
        (["Gen.0.1\tJohn.1.1\t5"], "must be positive"),  # chapter <= 0
        (["Gen.1.1\tJohn.1.1\tlots"], "non-integer votes"),  # bad votes
        (["Gen.1\tJohn.1.1\t5"], "malformed verse"),  # bad From ref
    ],
)
def test_malformed_rows_raise(tmp_path: Path, rows: list[str], match: str) -> None:
    with pytest.raises(LoaderError, match=match):
        build_database(tmp_path / "bible.db", [_corpus(tmp_path)], [_xref_dir(tmp_path, rows)])
