"""Notes loader behavior on synthetic fixtures: anchors, types, offsets, ordinals,
cross-refs, FTS, idempotency, loud validation, the multi-dir public/private union (ADR-0004),
and the licensing-safety proof (a clean build bakes the committed public notes but zero private
notes). No test depends on the copyrighted NET data (SPEC v4 §11)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import LoaderError, build_database
from loaderkit import book, chapter, translation, verse, write_translation
from noteskit import note, note_xref, notes_file, write_notes


def _corpus(tmp_path: Path) -> Path:
    """One translation (NETX) with the verses our synthetic notes anchor to."""
    tdir = tmp_path / "translations"
    netx = translation(
        "NETX",
        [
            book(
                "Gen",
                1,
                [chapter(1, [verse(1, "In the beginning God created the heavens and the earth.")])],
            ),
            book("John", 43, [chapter(3, [verse(16, "For God so loved the world.")])]),
            book("Rom", 45, [chapter(8, [verse(1, "There is therefore now no condemnation.")])]),
        ],
    )
    write_translation(tdir, netx)
    return tdir


def _build(tmp_path: Path, notes_payload: dict[str, object] | None) -> tuple[Path, object]:
    """Build a db from the corpus, optionally with one notes file under a private subdir."""
    notes_dir = tmp_path / "private" / "notes"
    if notes_payload is not None:
        write_notes(notes_dir, notes_payload)  # type: ignore[arg-type]
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[notes_dir])
    return tmp_path / "bible.db", stats


def _sample_notes() -> dict[str, object]:
    return notes_file(
        "NETX",
        [
            note(
                "John",
                3,
                16,
                "The Greek construction emphasizes degree, not manner.",
                type="tn",
                char_offset=8,
                marker="1",
                cross_references=[note_xref("Rom", 8, 1), note_xref("Gen", 1, 1, 2)],
            ),
            note("John", 3, 16, "A study note on divine love.", type="sn"),
            note("Gen", 1, 1, "A plain footnote with no type.", char_offset=3),
        ],
    )


# --- happy path ----------------------------------------------------------------------


def test_notes_land_with_correct_anchors_and_fields(tmp_path: Path) -> None:
    db_path, stats = _build(tmp_path, _sample_notes())
    assert stats.notes == 3  # type: ignore[attr-defined]
    assert stats.note_cross_references == 2  # type: ignore[attr-defined]

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT translation_id, book_id, chapter, verse, note_type, text, char_offset, marker "
        "FROM translator_notes WHERE marker = '1'"
    ).fetchone()
    assert row == (
        "NETX",
        "JHN",
        3,
        16,
        "tn",
        "The Greek construction emphasizes degree, not manner.",
        8,
        "1",
    )


def test_note_type_nullable_and_constrained(tmp_path: Path) -> None:
    db_path, _ = _build(tmp_path, _sample_notes())
    conn = sqlite3.connect(db_path)
    # The plain footnote on GEN 1:1 stored a NULL type (field omitted).
    null_types = conn.execute(
        "SELECT COUNT(*) FROM translator_notes WHERE note_type IS NULL"
    ).fetchone()[0]
    assert null_types == 1


def test_default_ordinal_sequences_within_a_verse(tmp_path: Path) -> None:
    db_path, _ = _build(tmp_path, _sample_notes())
    conn = sqlite3.connect(db_path)
    # Two notes anchor JHN 3:16 → ordinals 1 then 2 in array order; GEN 1:1 → 1.
    jhn = conn.execute(
        "SELECT ordinal FROM translator_notes WHERE book_id = 'JHN' ORDER BY id"
    ).fetchall()
    assert [r[0] for r in jhn] == [1, 2]
    gen = conn.execute("SELECT ordinal FROM translator_notes WHERE book_id = 'GEN'").fetchone()[0]
    assert gen == 1


def test_explicit_ordinal_is_honored(tmp_path: Path) -> None:
    payload = notes_file("NETX", [note("John", 3, 16, "Note.", ordinal=7)])
    db_path, _ = _build(tmp_path, payload)
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT ordinal FROM translator_notes").fetchone()[0] == 7


def test_cross_references_link_to_their_note(tmp_path: Path) -> None:
    db_path, _ = _build(tmp_path, _sample_notes())
    conn = sqlite3.connect(db_path)
    note_id = conn.execute("SELECT id FROM translator_notes WHERE marker = '1'").fetchone()[0]
    refs = conn.execute(
        "SELECT to_book_id, to_chapter, to_verse_start, to_verse_end "
        "FROM note_cross_references WHERE note_id = ? ORDER BY id",
        (note_id,),
    ).fetchall()
    assert refs == [("ROM", 8, 1, None), ("GEN", 1, 1, 2)]  # nullable end + a range


def test_notes_fts_is_searchable(tmp_path: Path) -> None:
    db_path, _ = _build(tmp_path, _sample_notes())
    conn = sqlite3.connect(db_path)
    hits = conn.execute(
        "SELECT t.book_id, t.chapter, t.verse FROM notes_fts f "
        "JOIN translator_notes t ON t.id = f.rowid "
        "WHERE notes_fts MATCH 'Greek'"
    ).fetchall()
    assert hits == [("JHN", 3, 16)]


def test_build_is_idempotent(tmp_path: Path) -> None:
    payload = _sample_notes()
    notes_dir = tmp_path / "private" / "notes"
    write_notes(notes_dir, payload)
    first = build_database(tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[notes_dir])
    second = build_database(tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[notes_dir])
    assert (first.notes, first.note_cross_references) == (
        second.notes,
        second.note_cross_references,
    )


# --- the licensing-safety proof (ADR-0004: public ships, private never does) ---------


def test_clean_build_bakes_public_notes_but_zero_private_notes(tmp_path: Path) -> None:
    """The stock-image case (ADR-0004): the committed public path bakes its notes, while the
    dual-ignored private path — absent in a clean build — bakes zero. Mirrors the loader's
    real ``[data/notes, data/private/notes]`` order with no ``data/private/`` present."""
    public_dir = tmp_path / "notes"
    private_dir = tmp_path / "private" / "notes"  # never created — the clean-build case
    write_notes(public_dir, notes_file("NETX", [note("John", 3, 16, "A public-domain footnote.")]))

    stats = build_database(
        tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[public_dir, private_dir]
    )

    assert stats.notes == 1  # the public note loaded
    conn = sqlite3.connect(tmp_path / "bible.db")
    # Every baked note came from the public file — none from the (absent) private path.
    texts = [r[0] for r in conn.execute("SELECT text FROM translator_notes")]
    assert texts == ["A public-domain footnote."]


def test_no_notes_dirs_yields_zero_notes(tmp_path: Path) -> None:
    """Defensive: omitting notes_dirs entirely → a notes-empty database."""
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])  # notes_dirs omitted
    assert stats.notes == 0
    assert stats.note_cross_references == 0
    conn = sqlite3.connect(tmp_path / "bible.db")
    assert conn.execute("SELECT COUNT(*) FROM translator_notes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM note_cross_references").fetchone()[0] == 0


def test_missing_notes_dir_is_not_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "private" / "notes"  # never created
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[missing])
    assert stats.notes == 0


# --- multi-dir union (ADR-0004) ------------------------------------------------------


def test_public_and_private_dirs_are_unioned_in_order(tmp_path: Path) -> None:
    """Both notes paths load; ids are assigned in dir order (public first), deterministically."""
    public_dir = tmp_path / "notes"
    private_dir = tmp_path / "private" / "notes"
    write_notes(public_dir, notes_file("NETX", [note("John", 3, 16, "Public note.")]))
    write_notes(private_dir, notes_file("NETX", [note("Gen", 1, 1, "Private note.")]))

    stats = build_database(
        tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[public_dir, private_dir]
    )

    assert stats.notes == 2
    conn = sqlite3.connect(tmp_path / "bible.db")
    ordered = conn.execute("SELECT text FROM translator_notes ORDER BY id").fetchall()
    assert [r[0] for r in ordered] == ["Public note.", "Private note."]  # public ids first


def test_dropping_private_dir_removes_exactly_the_private_notes(tmp_path: Path) -> None:
    """Rebuilding without the private path keeps the public notes and drops only the private."""
    public_dir = tmp_path / "notes"
    private_dir = tmp_path / "private" / "notes"
    write_notes(public_dir, notes_file("NETX", [note("John", 3, 16, "Public note.")]))
    write_notes(private_dir, notes_file("NETX", [note("Gen", 1, 1, "Private note.")]))

    both = build_database(
        tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[public_dir, private_dir]
    )
    public_only = build_database(
        tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[public_dir]
    )

    assert (both.notes, public_only.notes) == (2, 1)
    conn = sqlite3.connect(tmp_path / "bible.db")
    texts = [r[0] for r in conn.execute("SELECT text FROM translator_notes")]
    assert texts == ["Public note."]


# --- loud validation -----------------------------------------------------------------


def test_unknown_translation_fails_loudly(tmp_path: Path) -> None:
    payload = notes_file("NOPE", [note("John", 3, 16, "Note.")])
    with pytest.raises(LoaderError, match="not a loaded translation"):
        _build(tmp_path, payload)


def test_unknown_book_fails_loudly(tmp_path: Path) -> None:
    payload = notes_file("NETX", [note("Hezekiah", 1, 1, "Note.")])
    with pytest.raises(LoaderError, match="does not resolve to a known book"):
        _build(tmp_path, payload)


def test_unknown_note_type_fails_loudly(tmp_path: Path) -> None:
    payload = notes_file("NETX", [note("John", 3, 16, "Note.", type="bogus")])
    with pytest.raises(LoaderError, match="unknown note type"):
        _build(tmp_path, payload)


def test_empty_text_fails_loudly(tmp_path: Path) -> None:
    payload = notes_file("NETX", [note("John", 3, 16, "   ")])
    with pytest.raises(LoaderError, match="'text' is empty"):
        _build(tmp_path, payload)


def test_negative_char_offset_fails_loudly(tmp_path: Path) -> None:
    payload = notes_file("NETX", [note("John", 3, 16, "Note.", char_offset=-1)])
    with pytest.raises(LoaderError, match="char_offset"):
        _build(tmp_path, payload)


def test_invalid_json_fails_loudly(tmp_path: Path) -> None:
    notes_dir = tmp_path / "private" / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "NETX.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(LoaderError, match="invalid JSON"):
        build_database(tmp_path / "bible.db", [_corpus(tmp_path)], notes_dirs=[notes_dir])
