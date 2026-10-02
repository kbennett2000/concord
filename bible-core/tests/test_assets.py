"""A translation's images (ADR-0012) on synthetic fixtures: the assets loader's rules, the header
reader, ``get_asset``, and the note ``image`` that names one. Every image is made in the test
(``imagekit``); made-up text only — no book content (SPEC v8 §2)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from bible_core.assets import MAX_ASSET_BYTES, ImageError, image_header
from bible_core.db import connect_readonly
from bible_core.loader import LoaderError, build_database
from bible_core.queries import get_asset, get_notes, search_notes
from imagekit import jpeg, png
from loaderkit import book, chapter, translation, verse, write_translation
from noteskit import note, notes_file, write_notes

CHART = note(
    "Gen",
    12,
    10,
    "[Gen. 12:10-20](ref:GEN.12.10-20)",
    type="chart",
    label="Chart",
    title="A Made-up Chart",
    text_format="markdown",
    image="chart-01.jpg",
)


def _translations(tmp_path: Path) -> Path:
    tdir = tmp_path / "translations"
    for code in ("NETX", "PLNX"):
        shape = [book("Gen", 1, [chapter(12, [verse(10, "Made-up verse words.")])])]
        write_translation(tdir, translation(code, shape))
    return tdir


def _assets(tmp_path: Path, files: dict[str, bytes]) -> Path:
    """Write ``{"NETX/chart-01.jpg": b"…"}`` under ``tmp_path/private/assets``."""
    root = tmp_path / "private" / "assets"
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build(
    tmp_path: Path, files: dict[str, bytes], notes: list[dict[str, Any]] | None = None
) -> sqlite3.Connection:
    notes_dir = tmp_path / "private" / "notes"
    if notes is not None:
        write_notes(notes_dir, notes_file("NETX", notes))
    build_database(
        tmp_path / "bible.db",
        [_translations(tmp_path)],
        notes_dirs=[notes_dir],
        assets_dirs=[_assets(tmp_path, files)],
    )
    return connect_readonly(tmp_path / "bible.db")


# --- the header reader -------------------------------------------------------------------


def test_the_header_reader_names_type_and_size() -> None:
    assert image_header(jpeg(20, 10)) == ("image/jpeg", 20, 10)
    assert image_header(png(5, 4)) == ("image/png", 5, 4)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"GIF89a\x01\x00\x01\x00", "not a JPEG or PNG"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "not a JPEG or PNG"),
        (jpeg()[:-2], "no end-of-image marker"),
        (b"\xff\xd8\xff\xd9", "no frame header"),
        (png()[:-12], "no IEND chunk"),
        (png().replace(b"IHDR", b"IHDX"), "no IHDR chunk"),
        (jpeg(9000, 10), "outside 1 to 8192 pixels"),
        (png(0, 3), "outside 1 to 8192 pixels"),
    ],
)
def test_the_header_reader_refuses_anything_else(data: bytes, message: str) -> None:
    with pytest.raises(ImageError, match=message):
        image_header(data)


# --- loading ------------------------------------------------------------------------------


def test_jpeg_and_png_load_with_their_type_size_and_exact_bytes(tmp_path: Path) -> None:
    chart, diagram = jpeg(20, 10), png(5, 4)
    conn = _build(tmp_path, {"NETX/chart-01.jpg": chart, "NETX/diagram_2.png": diagram})
    stored = get_asset(conn, "NETX", "chart-01.jpg")
    assert stored is not None
    assert (stored.media_type, stored.width, stored.height, stored.data) == (
        "image/jpeg",
        20,
        10,
        chart,
    )
    other = get_asset(conn, "NETX", "diagram_2.png")
    assert other is not None and (other.media_type, other.data) == ("image/png", diagram)


def test_an_unknown_name_or_translation_is_absent(tmp_path: Path) -> None:
    conn = _build(tmp_path, {"NETX/chart-01.jpg": jpeg()})
    assert get_asset(conn, "NETX", "chart-02.jpg") is None
    assert get_asset(conn, "NETX", "CHART-01.JPG") is None  # names match exactly
    assert get_asset(conn, "PLNX", "chart-01.jpg") is None  # another translation's


def test_a_missing_assets_directory_loads_nothing(tmp_path: Path) -> None:
    db = tmp_path / "bible.db"
    stats = build_database(db, [_translations(tmp_path)], assets_dirs=[tmp_path / "nowhere"])
    assert stats.assets == 0
    assert (
        connect_readonly(db).execute("SELECT COUNT(*) FROM translation_assets").fetchone()[0] == 0
    )


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"NETX/chart-01.png": jpeg()}, r"NETX/chart-01\.png: the file is a JPEG, but its name"),
        ({"NETX/chart-01.jpg": png()}, r"the file is a PNG, but its name ends in \.jpg"),
        ({"NETX/chart.gif": b"GIF89a"}, "not a valid asset name"),
        ({"NETX/chart.svg": b"<svg/>"}, "not a valid asset name"),
        ({"NETX/chart.jpg": b"GIF89a\x01\x00"}, r"NETX/chart\.jpg: not a JPEG or PNG"),
        ({"NETX/cut.jpg": jpeg()[:-2]}, r"cut\.jpg: not a complete JPEG"),
        ({"NETX/empty.png": b""}, r"empty\.png: the file is empty"),
        ({"NETX/big.png": png() + b"\x00" * MAX_ASSET_BYTES}, "over the 2,097,152-byte limit"),
        ({"NETX/Chart-01.jpg": jpeg()}, "not a valid asset name"),
        ({"NETX/chart 01.jpg": jpeg()}, "not a valid asset name"),
        ({"NETX/.hidden.jpg": jpeg()}, "not a valid asset name"),
        ({"NETX/chart-01": jpeg()}, "not a valid asset name"),
        ({"NETX/inner/chart-01.jpg": jpeg()}, r"NETX/inner: not a file \(no sub-folders\)"),
        ({"loose.jpg": jpeg()}, r"assets/loose\.jpg: only translation folders"),
        ({"XYZ/chart-01.jpg": jpeg()}, "translation 'XYZ' is not a loaded translation"),
        ({"netx/chart-01.jpg": jpeg()}, "translation 'netx' is not a loaded translation"),
    ],
)
def test_a_bad_asset_fails_the_build_naming_the_file(
    tmp_path: Path, files: dict[str, bytes], message: str
) -> None:
    with pytest.raises(LoaderError, match=message):
        _build(tmp_path, files)


def test_one_name_in_two_assets_directories_fails(tmp_path: Path) -> None:
    first = _assets(tmp_path / "a", {"NETX/chart-01.jpg": jpeg()})
    second = _assets(tmp_path / "b", {"NETX/chart-01.jpg": jpeg()})
    with pytest.raises(LoaderError, match="already has an asset by that name"):
        build_database(
            tmp_path / "bible.db", [_translations(tmp_path)], assets_dirs=[first, second]
        )


# --- a note's image -----------------------------------------------------------------------


def test_a_note_image_naming_an_asset_round_trips(tmp_path: Path) -> None:
    conn = _build(tmp_path, {"NETX/chart-01.jpg": jpeg()}, [CHART])
    (stored,) = get_notes(conn, "NETX", "GEN", 12)
    assert (stored.note_type, stored.label, stored.image) == ("chart", "Chart", "chart-01.jpg")
    (hit,) = search_notes(conn, "Gen", "NETX", None, None, 10, 0).hits
    assert hit.image == "chart-01.jpg"


def test_a_note_image_naming_a_missing_asset_fails(tmp_path: Path) -> None:
    with pytest.raises(
        LoaderError,
        match=r"NETX\.json notes\[0\]: 'image' names 'chart-01\.jpg', but translation 'NETX' "
        "has no asset by that name",
    ):
        _build(tmp_path, {"NETX/chart-02.jpg": jpeg()}, [CHART])


def test_a_note_image_naming_another_translations_asset_fails(tmp_path: Path) -> None:
    with pytest.raises(LoaderError, match="translation 'NETX' has no asset by that name"):
        _build(tmp_path, {"PLNX/chart-01.jpg": jpeg()}, [CHART])
