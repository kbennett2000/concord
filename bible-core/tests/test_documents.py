"""A translation's documents (ADR-0012) on synthetic fixtures: the documents loader's rules, the
images a document's text places, ``list_documents`` / ``get_document`` and ``document_count``.
Made-up text and made-up images only (``imagekit``) — no book content (SPEC v8 §2)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from bible_core.db import connect_readonly
from bible_core.loader import LoaderError, build_database
from bible_core.queries import (
    DocumentImageRow,
    DocumentSummaryRow,
    get_document,
    get_translations,
    list_documents,
)
from imagekit import jpeg, png
from loaderkit import book, chapter, translation, verse, write_translation

FIGURE = jpeg(30, 6)
PLAN = png(4, 3)


def document(
    slug: str,
    kind: str = "about",
    *,
    title: str = "A Made-up Title",
    book: str | None = None,
    ordinal: int = 1,
    text: str = "Made-up words.",
) -> dict[str, Any]:
    payload: dict[str, Any] = {"slug": slug, "kind": kind, "title": title, "ordinal": ordinal}
    if book is not None:
        payload["book"] = book
    payload["text"] = text
    return payload


def introduction(code: str, ordinal: int, text: str = "Made-up words.") -> dict[str, Any]:
    return document(
        f"introduction-{code.lower()}",
        "book-introduction",
        title=f"Made-up {code}",
        book=code,
        ordinal=ordinal,
        text=text,
    )


def _translations(tmp_path: Path) -> Path:
    tdir = tmp_path / "translations"
    for code in ("DOCX", "PLNX"):
        shape = [book("Gen", 1, [chapter(1, [verse(1, "Made-up verse words.")])])]
        write_translation(tdir, translation(code, shape))
    return tdir


def _write(directory: Path, name: str, payload: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def _build(
    tmp_path: Path,
    documents: list[dict[str, Any]],
    translation_id: str = "DOCX",
    extra: dict[str, Any] | None = None,
) -> sqlite3.Connection:
    """Build with ``documents`` for ``translation_id`` (plus ``extra`` files by name), DOCX
    holding a JPEG and a PNG and PLNX a JPEG of its own."""
    assets = tmp_path / "private" / "assets"
    for rel, data in {
        "DOCX/figure-gen.jpg": FIGURE,
        "DOCX/plan.png": PLAN,
        "PLNX/other.jpg": jpeg(2, 2),
    }.items():
        (assets / rel).parent.mkdir(parents=True, exist_ok=True)
        (assets / rel).write_bytes(data)
    documents_dir = tmp_path / "private" / "documents"
    _write(
        documents_dir,
        f"{translation_id}.json",
        {"translation": translation_id, "documents": documents},
    )
    for name, payload in (extra or {}).items():
        _write(documents_dir, name, payload)
    build_database(
        tmp_path / "bible.db",
        [_translations(tmp_path)],
        assets_dirs=[assets],
        documents_dirs=[documents_dir],
    )
    return connect_readonly(tmp_path / "bible.db")


# --- loading ---------------------------------------------------------------------------------


def test_a_document_round_trips_with_the_images_its_text_places(tmp_path: Path) -> None:
    text = (
        "## A MADE-UP HEAD\n\nMade-up words on [chapter 1](ref:GEN.1).\n\n"
        "![A made-up caption](asset:figure-gen.jpg)\n\n![](asset:plan.png)\n\n"
        "![Again](asset:figure-gen.jpg)"
    )
    conn = _build(tmp_path, [introduction("Gen", 1, text)])
    row = get_document(conn, "DOCX", "introduction-gen")
    assert row is not None
    assert (row.translation_id, row.slug, row.kind, row.title, row.book_id, row.ordinal) == (
        "DOCX",
        "introduction-gen",
        "book-introduction",
        "Made-up Gen",
        "GEN",
        1,
    )
    assert row.text == text
    # in order of first use, each once, with the asset's type and size
    assert row.images == (
        DocumentImageRow("figure-gen.jpg", "image/jpeg", 30, 6),
        DocumentImageRow("plan.png", "image/png", 4, 3),
    )


def test_text_and_title_are_trimmed_and_unknown_keys_ignored(tmp_path: Path) -> None:
    payload = document("made-up", title="  A Title  ", text="\n Made-up words. \n")
    payload["images"] = ["ignored.jpg"]  # images come from the text, never supplied
    conn = _build(tmp_path, [payload])
    row = get_document(conn, "DOCX", "made-up")
    assert row is not None
    assert (row.title, row.text, row.images) == ("A Title", "Made-up words.", ())


def test_the_list_is_in_kind_then_ordinal_order(tmp_path: Path) -> None:
    conn = _build(
        tmp_path,
        [
            document("closing-words", "about", ordinal=2),
            introduction("Exo", 2),
            document("opening-words", "about", ordinal=1),
            document("the-plan", "reading-plan"),
            introduction("Gen", 1),
            document("a-preface", "front-matter"),
        ],
    )
    assert [d.slug for d in list_documents(conn, "DOCX")] == [
        "a-preface",
        "the-plan",
        "introduction-gen",
        "introduction-exo",
        "opening-words",
        "closing-words",
    ]
    assert list_documents(conn, "DOCX")[2] == DocumentSummaryRow(
        "introduction-gen", "book-introduction", "Made-up Gen", "GEN", 1
    )


def test_the_filters_narrow_and_combine(tmp_path: Path) -> None:
    conn = _build(tmp_path, [introduction("Gen", 1), introduction("Exo", 2), document("x")])
    assert [d.slug for d in list_documents(conn, "DOCX", book_id="EXO")] == ["introduction-exo"]
    assert [d.slug for d in list_documents(conn, "DOCX", kind="about")] == ["x"]
    assert list_documents(conn, "DOCX", book_id="EXO", kind="about") == []
    assert list_documents(conn, "PLNX") == []


def test_a_slug_matches_exactly(tmp_path: Path) -> None:
    conn = _build(tmp_path, [document("made-up")])
    assert get_document(conn, "DOCX", "made-up") is not None
    assert get_document(conn, "DOCX", "Made-Up") is None
    assert get_document(conn, "PLNX", "made-up") is None


def test_document_count_per_translation(tmp_path: Path) -> None:
    conn = _build(tmp_path, [introduction("Gen", 1), document("x")])
    assert {t.id: t.document_count for t in get_translations(conn)} == {"DOCX": 2, "PLNX": 0}


def test_two_files_load_side_by_side(tmp_path: Path) -> None:
    other = {"translation": "PLNX", "documents": [document("made-up", text="![](asset:other.jpg)")]}
    conn = _build(tmp_path, [document("made-up")], extra={"PLNX.json": other})
    plnx = get_document(conn, "PLNX", "made-up")
    assert plnx is not None and [i.name for i in plnx.images] == ["other.jpg"]
    assert get_document(conn, "DOCX", "made-up") is not None


def test_a_missing_directory_loads_nothing(tmp_path: Path) -> None:
    stats = build_database(
        tmp_path / "bible.db",
        [_translations(tmp_path)],
        documents_dirs=[tmp_path / "private" / "documents"],
    )
    assert stats.documents == 0


# --- refusals ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("documents", "message"),
    [
        ([document("Made-Up")], r"slug 'Made-Up' is not lower-case"),
        ([document("-made-up")], r"slug '-made-up' is not lower-case"),
        ([document("made_up")], r"slug 'made_up' is not lower-case"),
        ([document("a" * 65)], r"is not lower-case"),
        ([document("x", "preface")], r"unknown kind 'preface'"),
        ([document("x", title=" ")], r"'title' is empty"),
        ([document("x", text="  ")], r"'text' is empty"),
        ([{**document("x"), "ordinal": 0}], r"'ordinal' must be >= 1"),
        ([{**document("x"), "ordinal": "1"}], r"'ordinal' must be an integer"),
        ([{**document("x"), "ordinal": True}], r"'ordinal' must be an integer"),
        ([{"slug": "x", "kind": "about", "ordinal": 1}], r"missing required field 'title'"),
        ([document("x", "book-introduction")], r"a book introduction needs its 'book'"),
        ([document("x", book="Gen")], r"only a book introduction has a 'book'"),
        ([introduction("Hezekiah", 1)], r"book 'Hezekiah' does not resolve"),
        ([document("x"), document("x", ordinal=2)], r"already has a document with this slug"),
        ([document("x"), document("y")], r"already has ordinal 1 among its 'about' documents"),
        (
            [introduction("Gen", 1), {**introduction("Genesis", 2), "slug": "again"}],
            r"already has an introduction to GEN",
        ),
        ([document("x", text="[a](ref:GEN.1.x)")], r"not in the ADR-0011 grammar"),
        ([document("x", text="[a](ref:XYZ.1)")], r"names unknown book 'XYZ'"),
        ([document("x", text="[a](ref:GEN.3-2)")], r"ends before it starts"),
        ([document("x", text="![a](asset:none.jpg)")], r"asset:none.jpg names no asset"),
        ([document("x", text="![a](asset:other.jpg)")], r"names no asset of translation 'DOCX'"),
        ([document("x", text="[a](asset:plan.png)")], r"asset:plan.png is used as a link"),
        ([document("x", text="See ](asset:plan.png)")], r"asset:plan.png is used as a link"),
        ([document("x", text=r"![a \[b](asset:none.png)")], r"asset:none.png names no asset"),
    ],
)
def test_a_bad_document_fails_the_build_naming_the_file(
    tmp_path: Path, documents: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(LoaderError, match=message) as info:
        _build(tmp_path, documents)
    assert "DOCX.json" in str(info.value)


def test_an_image_alt_text_may_hold_escaped_brackets(tmp_path: Path) -> None:
    conn = _build(tmp_path, [document("x", text=r"![a \[made-up\] b](asset:plan.png)")])
    row = get_document(conn, "DOCX", "x")
    assert row is not None and [i.name for i in row.images] == ["plan.png"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"translation": "NOPE", "documents": []}, r"translation 'NOPE', which is not a loaded"),
        ({"documents": []}, r"missing required field 'translation'"),
        ({"translation": "DOCX", "documents": {}}, r"'documents' must be a list"),
        ([], r"expected a JSON object"),
    ],
)
def test_a_bad_file_fails_the_build(tmp_path: Path, payload: Any, message: str) -> None:
    with pytest.raises(LoaderError, match=message):
        _build(tmp_path, [], extra={"bad.json": payload})


def test_a_slug_taken_in_another_file_fails(tmp_path: Path) -> None:
    again = {"translation": "DOCX", "documents": [document("x", ordinal=2)]}
    with pytest.raises(LoaderError, match=r"DOCX2\.json document 'x'.*already has a document"):
        _build(tmp_path, [document("x")], extra={"DOCX2.json": again})


def test_invalid_json_fails_naming_the_file(tmp_path: Path) -> None:
    documents_dir = tmp_path / "private" / "documents"
    documents_dir.mkdir(parents=True)
    (documents_dir / "DOCX.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(LoaderError, match=r"DOCX\.json: invalid JSON"):
        build_database(
            tmp_path / "bible.db", [_translations(tmp_path)], documents_dirs=[documents_dir]
        )
