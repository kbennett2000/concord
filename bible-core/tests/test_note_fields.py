"""The v8 note fields (ADR-0011) on synthetic fixtures: label, title, text_format, passages, the
reserved image, the article/chart types, ref: links in Markdown text, and note_count. Each round-
trips through the loader and the queries; every bad value fails the build loudly. Made-up text only
— no EMB or NET content (SPEC v8 §2)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from bible_core.db import connect_readonly
from bible_core.loader import LoaderError, build_database
from bible_core.queries import NotePassageRow, get_notes, get_translations, search_notes
from loaderkit import book, chapter, translation, verse, write_translation
from noteskit import note, note_passage, notes_file, write_notes

_SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "notes-sample.json"

ARTICLE = note(
    "Gen",
    12,
    10,
    "A made-up *feature* on [the famine](ref:GEN.12.10-20) and [chapter 20](ref:GEN.20).",
    type="article",
    label="Made-up Series",
    title="A Made-up Title",
    text_format="markdown",
    passages=[note_passage(12, 10, 12, 20), note_passage(20, 1, 21, 3)],
)
PLAIN = note("Gen", 12, 10, "A made-up plain note.", type="tn")


def _translations(tmp_path: Path, codes: tuple[str, ...] = ("NETX", "PLNX")) -> Path:
    """Translations sharing one tiny shape; only NETX gets notes."""
    tdir = tmp_path / "translations"
    for code in codes:
        shape = [book("Gen", 1, [chapter(12, [verse(10, "Made-up verse words.")])])]
        write_translation(tdir, translation(code, shape))
    return tdir


def _build(tmp_path: Path, notes: list[dict[str, Any]]) -> sqlite3.Connection:
    notes_dir = tmp_path / "private" / "notes"
    write_notes(notes_dir, notes_file("NETX", notes))
    build_database(tmp_path / "bible.db", [_translations(tmp_path)], notes_dirs=[notes_dir])
    return connect_readonly(tmp_path / "bible.db")


# --- round trips ---------------------------------------------------------------------


def test_every_new_field_round_trips_through_the_passage_read(tmp_path: Path) -> None:
    article, _ = get_notes(_build(tmp_path, [ARTICLE, PLAIN]), "NETX", "GEN", 12)
    assert article.note_type == "article"
    assert (article.label, article.title, article.text_format) == (
        "Made-up Series",
        "A Made-up Title",
        "markdown",
    )
    assert article.passages == (NotePassageRow(12, 10, 12, 20), NotePassageRow(20, 1, 21, 3))
    assert article.image is None
    assert article.text == ARTICLE["text"]  # Markdown and ref: links stored verbatim


def test_a_note_without_the_new_fields_reads_them_as_null_and_empty(tmp_path: Path) -> None:
    _, plain = get_notes(_build(tmp_path, [ARTICLE, PLAIN]), "NETX", "GEN", 12)
    assert (plain.label, plain.title, plain.text_format, plain.passages, plain.image) == (
        None,
        None,
        None,
        (),
        None,
    )


def test_search_hits_carry_the_new_fields(tmp_path: Path) -> None:
    conn = _build(tmp_path, [ARTICLE, PLAIN])
    (article,) = search_notes(conn, "feature", None, None, None, 10, 0).hits
    assert (article.label, article.title, article.text_format, article.image) == (
        "Made-up Series",
        "A Made-up Title",
        "markdown",
        None,
    )
    assert article.passages == (NotePassageRow(12, 10, 12, 20), NotePassageRow(20, 1, 21, 3))
    (plain,) = search_notes(conn, "plain", None, None, None, 10, 0).hits
    assert (plain.label, plain.title, plain.text_format, plain.passages, plain.image) == (
        None,
        None,
        None,
        (),
        None,
    )


def test_article_and_chart_types_load_and_filter(tmp_path: Path) -> None:
    chart = note("Gen", 12, 10, "A made-up chart caption.", type="chart", label="Chart")
    conn = _build(tmp_path, [ARTICLE, chart])
    for note_type in ("article", "chart"):
        hits = search_notes(conn, "made", None, note_type, None, 10, 0).hits
        assert [h.note_type for h in hits] == [note_type]


def test_note_count_per_translation(tmp_path: Path) -> None:
    conn = _build(tmp_path, [ARTICLE, PLAIN])
    assert {t.id: t.note_count for t in get_translations(conn)} == {"NETX": 2, "PLNX": 0}


def test_the_sample_notes_file_loads(tmp_path: Path) -> None:
    """examples/notes-sample.json — the runnable example docs/API.md points at — stays valid."""
    tdir = tmp_path / "translations"
    shape = [
        book("Gen", 1, [chapter(1, [verse(1, "Made-up words.")])]),
        book("John", 43, [chapter(3, [verse(16, "Made-up words.")])]),
    ]
    write_translation(tdir, translation("KJV", shape))
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    shutil.copy(_SAMPLE, notes_dir / "KJV.json")
    stats = build_database(tmp_path / "bible.db", [tdir], notes_dirs=[notes_dir])
    assert stats.notes >= 1


# --- ref: links (ADR-0011 §3) --------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        "JHN.3",  # whole chapter
        "GEN.12-14",  # chapter range
        "JHN.3.16",  # single verse
        "JHN.3.16-18",  # range in a chapter
        "JHN.3.16-4.2",  # cross-chapter range
        "1CO.13.4-7",  # a numbered book's code
        "JHN.3.16-16",  # a one-verse range is not descending
    ],
)
def test_every_ref_form_loads(tmp_path: Path, target: str) -> None:
    linked = note("Gen", 12, 10, f"See [this](ref:{target}).", text_format="markdown")
    assert len(get_notes(_build(tmp_path, [linked]), "NETX", "GEN", 12)) == 1


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("jhn.3.16", "not in the ADR-0011 grammar"),  # lower case
        ("John.3.16", "not in the ADR-0011 grammar"),  # an alias, not a USFM code
        ("JHN.03.16", "not in the ADR-0011 grammar"),  # leading zero
        ("JHN.3.0", "not in the ADR-0011 grammar"),  # verse 0
        ("JHN.3.16-", "not in the ADR-0011 grammar"),  # dangling dash
        ("JHN 3:16", "not in the ADR-0011 grammar"),  # Concord's display form
        ("JHN.3-4.2", "not in the ADR-0011 grammar"),  # chapter-to-verse (ADR-0010) not a form
        ("JHN", "not in the ADR-0011 grammar"),  # no chapter
        ("XYZ.1.1", "unknown book 'XYZ'"),
        ("JHN.3.18-16", "ends before it starts"),
        ("JHN.4.1-3.16", "ends before it starts"),
        ("GEN.14-12", "ends before it starts"),
    ],
)
def test_a_bad_ref_target_fails_loudly(tmp_path: Path, target: str, message: str) -> None:
    linked = note("Gen", 12, 10, f"See [this](ref:{target}).", text_format="markdown")
    with pytest.raises(LoaderError, match=message):
        _build(tmp_path, [linked])


def test_ref_links_in_plain_text_are_not_checked(tmp_path: Path) -> None:
    unchecked = note("Gen", 12, 10, "A made-up [link](ref:not-a-ref) in plain text.")
    assert len(get_notes(_build(tmp_path, [unchecked]), "NETX", "GEN", 12)) == 1


# --- loud validation -----------------------------------------------------------------

_GOOD_PASSAGE = note_passage(12, 10, 12, 20)


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ({"label": 5}, "'label' must be a string"),
        ({"label": "   "}, "'label' is empty"),
        ({"title": ["A title"]}, "'title' must be a string"),
        ({"title": ""}, "'title' is empty"),
        ({"text_format": "plain"}, "unknown text_format 'plain'"),
        ({"text_format": "Markdown"}, "unknown text_format 'Markdown'"),
        ({"text_format": "html"}, "unknown text_format 'html'"),
        ({"text_format": 1}, "'text_format' must be a string"),
        ({"passages": _GOOD_PASSAGE}, "'passages' must be a list"),
        ({"passages": ["12:10-20"]}, r"passages\[0\]: expected a JSON object"),
        ({"passages": [{**_GOOD_PASSAGE, "end_verse": None}]}, "'end_verse' must be an integer"),
        ({"passages": [{"start_chapter": 12, "start_verse": 10}]}, "missing required field"),
        ({"passages": [{**_GOOD_PASSAGE, "start_verse": True}]}, "must be an integer"),
        ({"passages": [{**_GOOD_PASSAGE, "start_chapter": 0}]}, "must be positive"),
        ({"passages": [note_passage(12, 20, 12, 10)]}, r"ends \(12:10\) before it starts"),
        ({"passages": [note_passage(13, 1, 12, 30)]}, r"ends \(12:30\) before it starts"),
        ({"image": "chart.png"}, "'image' is reserved until the images slice"),
    ],
)
def test_a_bad_value_fails_loudly(tmp_path: Path, bad: dict[str, Any], message: str) -> None:
    with pytest.raises(LoaderError, match=message):
        _build(tmp_path, [PLAIN, {**PLAIN, **bad}])


def test_errors_name_the_file_and_note(tmp_path: Path) -> None:
    with pytest.raises(LoaderError, match=r"NETX\.json notes\[1\]: 'label' is empty"):
        _build(tmp_path, [PLAIN, {**PLAIN, "label": ""}])


def test_a_null_image_and_null_fields_are_accepted(tmp_path: Path) -> None:
    nulls = {**PLAIN, "label": None, "title": None, "text_format": None, "image": None}
    (stored,) = get_notes(_build(tmp_path, [{**nulls, "passages": None}]), "NETX", "GEN", 12)
    assert (stored.label, stored.passages, stored.image) == (None, (), None)
