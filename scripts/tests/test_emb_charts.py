"""EMB's charts on synthetic pdftohtml XML (V8-S4b; made-up text and made-up images only): the
Charts Index, each entry's image and its bytes, where a chart stands and the note it becomes, the
order at a shared spot, the image census, the asset files, and the EPUB witness."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from bible_core.loader import build_database
from emb_convert.charts import ChartRegion, find_charts
from emb_convert.clean import Fixes, PublicWords
from emb_convert.convert import stale_assets, translation_payload, write_assets
from emb_convert.epub_charts import cross_check_epub_charts
from emb_convert.layout import find_layout
from emb_convert.notes import NotesResult, build_notes, notes_payload
from emb_convert.pdfxml import parse_pdf_xml
from emb_convert.skeleton import load_skeleton
from emb_convert.text import ParseResult, parse_bible
from imagekit import jpeg
from pdfxmlkit import (
    CHARTS_PAGE,
    FEATURES_PAGE,
    WBSA_PAGE,
    Img,
    T,
    body,
    document,
    header,
    start,
    verse_texts,
    vnum,
)

GEN = start("GEN") + 1
TOPIC = WBSA_PAGE + 1

V1 = "A made-up first verse."
V2 = "Second made-up verse that runs on to the end."
V3 = "A made-up third verse."
V4 = "A made-up fourth verse."

Pages = dict[int, list[T | Img]]


def _images(tmp_path: Path) -> dict[str, Path]:
    """Made-up charts in three shapes, an introduction figure, an icon, a full page."""
    made = {
        "a": jpeg(1024, 693),
        "b": jpeg(671, 963),
        "c": jpeg(1024, 726),
        "figure": jpeg(1024, 170),
        "icon": jpeg(150, 20),
        "page": jpeg(682, 1024),
    }
    paths: dict[str, Path] = {}
    for name, data in made.items():
        paths[name] = tmp_path / f"{name}.jpg"
        paths[name].write_bytes(data)
    return paths


def _index(*entries: list[T]) -> list[T | Img]:
    return [T("CHARTS INDEX", 54, 134, 15, bold=True), *(i for e in entries for i in e)]


def _entry(top: int, title: str, page: int, reference: str, ref_page: int) -> list[T]:
    return [
        T(title, top, 38, blue=True, link=page),
        T(" (", top, 140, link=page),
        T(reference, top, 147, blue=True, link=ref_page),
        T(")", top, 210),
    ]


def pages(img: dict[str, Path]) -> Pages:
    """Genesis 1–2: chart 1 closes 1:1-2; chart 2 (1:3, indexed a page early) stands after 1:4;
    chart 3 (chapters 1–2, its reference wrapped in the index) stands inside, after 2:1."""
    return {
        1: [Img(0, str(img["page"]), 499, 380, 0)],  # the front matter's cover
        GEN: [
            Img(30, str(img["figure"]), 85),  # an introduction-sized figure
            *header("GEN", 1, top=130),
            vnum("1", 170),
            body(V1, 170, 45),
            vnum("2", 190),
            body(V2, 190, 45),
            Img(210, str(img["a"])),
        ],
        GEN + 1: [
            vnum("3", 60),
            body(V3, 60, 45),
            Img(80, str(img["icon"]), 20, 135, 205),  # a callout icon
            vnum("4", 120),
            body(V4, 120, 45),
        ],
        GEN + 2: [Img(37, str(img["b"]), 423)],
        GEN + 3: [
            *header("GEN", 2),
            vnum("1", 100),
            body("Chapter two opens.", 100, 45),
            Img(120, str(img["c"]), 325),
            vnum("2", 450),
            body("It goes on.", 450, 45),
            vnum("3", 470),
            body("It ends.", 470, 45),
        ],
        GEN + 4: [Img(37, str(img["page"]), 423)],  # a page of its own, no entry's
        FEATURES_PAGE + 1: [Img(37, str(img["icon"]), 40, 303)],  # a feature-region banner
        CHARTS_PAGE: _index(
            _entry(72, "A Made-up Chart", GEN, "Gen. 1:1-2", GEN),
            _entry(86, "Plim Vosk Drane", GEN + 1, "Gen. 1:3", GEN + 1),
            [
                T("Another Made-up", 101, 38, blue=True, link=GEN + 3),
                T(" (", 101, 120, link=GEN + 3),
                T("Gen. 1–", 101, 127, blue=True, link=GEN),
            ],
            [T("2", 115, 38, blue=True, link=GEN), T(")", 115, 45)],
        ),
    }


def run(given: Mapping[int, Sequence[T | Img]]) -> tuple[ChartRegion, ParseResult, NotesResult]:
    doc = parse_pdf_xml(document(given, [(CHARTS_PAGE, "Charts Index")]))
    layout = find_layout(doc)
    region = find_charts(doc, layout)
    words = PublicWords(())
    result = parse_bible(doc, layout, Fixes(), words, region.images)
    return region, result, build_notes(doc, layout, result, words, load_skeleton(), region)


def charts_of(notes: NotesResult) -> list[dict[str, Any]]:
    return [note for note in notes.payload if note["type"] == "chart"]


# -- the index, the images and their bytes ---------------------------------------------------


def test_the_index_claims_each_charts_image_and_reads_its_bytes(tmp_path: Path) -> None:
    img = _images(tmp_path)
    region, _, _ = run(pages(img))
    assert [(c.number, c.title, c.reference, c.page) for c in region.charts] == [
        (1, "A Made-up Chart", "Gen. 1:1-2", GEN),
        (2, "Plim Vosk Drane", "Gen. 1:3", GEN + 1),
        (3, "Another Made-up", "Gen. 1–2", GEN + 3),  # wrapped after its dash, joined
    ]
    assert [c.image.page if c.image else None for c in region.charts] == [GEN, GEN + 2, GEN + 3]
    first = region.charts[0]
    assert first.data == img["a"].read_bytes()
    assert (first.media_type, first.width, first.height, first.name) == (
        "image/jpeg",
        1024,
        693,
        "chart-01.jpg",
    )
    assert not region.errors and not region.unclaimed


def test_every_image_in_the_pdf_is_counted_by_kind(tmp_path: Path) -> None:
    region, _, _ = run(pages(_images(tmp_path)))
    assert region.census == Counter(
        {
            "chart": 3,
            "front matter": 1,
            "introduction figure": 1,
            "callout icon": 1,
            "page of its own": 1,
            "feature region": 1,
        }
    )


# -- where each chart stands, and its note ---------------------------------------------------


def test_each_chart_becomes_a_note_where_its_image_stands(tmp_path: Path) -> None:
    _, _, notes = run(pages(_images(tmp_path)))
    found = notes.charts
    assert found.ok
    assert found.shapes == Counter({"range": 1, "verse": 1, "whole chapters": 1})
    assert found.places == Counter({"closes its passage": 1, "after it": 1, "inside it": 1})
    assert charts_of(notes) == [
        {
            "book": "GEN",
            "chapter": 1,
            "verse": 2,
            "type": "chart",
            "label": "Chart",
            "title": "A Made-up Chart",
            "text": "[Gen. 1:1-2](ref:GEN.1.1-2)",
            "text_format": "markdown",
            "char_offset": len(V2),
            "passages": [{"start_chapter": 1, "start_verse": 1, "end_chapter": 1, "end_verse": 2}],
            "image": "chart-01.jpg",
        },
        {
            "book": "GEN",
            "chapter": 1,
            "verse": 4,  # it stands after its verse: the passage still says which one
            "type": "chart",
            "label": "Chart",
            "title": "Plim Vosk Drane",
            "text": "[Gen. 1:3](ref:GEN.1.3)",
            "text_format": "markdown",
            "char_offset": len(V4),
            "passages": [{"start_chapter": 1, "start_verse": 3, "end_chapter": 1, "end_verse": 3}],
            "image": "chart-02.jpg",
        },
        {
            "book": "GEN",
            "chapter": 2,
            "verse": 1,
            "type": "chart",
            "label": "Chart",
            "title": "Another Made-up",
            "text": "[Gen. 1–2](ref:GEN.1-2)",
            "text_format": "markdown",
            "char_offset": len("Chapter two opens."),
            "passages": [{"start_chapter": 1, "start_verse": 1, "end_chapter": 2, "end_verse": 3}],
            "image": "chart-03.jpg",
        },
    ]
    assert sorted(found.assets) == ["chart-01.jpg", "chart-02.jpg", "chart-03.jpg"]


def test_a_single_verse_chart_standing_at_its_verse_has_no_passages(tmp_path: Path) -> None:
    given = pages(_images(tmp_path))
    given[CHARTS_PAGE][1:5] = _entry(72, "A Made-up Chart", GEN, "Gen. 1:2", GEN)
    _, _, notes = run(given)
    assert "passages" not in charts_of(notes)[0]
    assert notes.charts.passages == 2


def test_the_text_pass_is_the_same_with_the_images_in_it(tmp_path: Path) -> None:
    given = pages(_images(tmp_path))
    bare = {n: [i for i in items if isinstance(i, T)] for n, items in given.items()}
    _, with_charts, _ = run(given)
    doc = parse_pdf_xml(document(bare, [(CHARTS_PAGE, "Charts Index")]))
    without = parse_bible(doc, find_layout(doc), Fixes(), PublicWords(()))
    assert verse_texts(with_charts) == verse_texts(without)
    assert with_charts.markers == without.markers
    assert parse_pdf_xml(document(given)).items == doc.items


# -- what blocks the run -----------------------------------------------------------------------


def _blocked(notes: NotesResult) -> bool:
    return not notes.charts.ok and not notes.ok


def test_a_chart_sized_image_no_entry_claims_blocks_the_run(tmp_path: Path) -> None:
    img = _images(tmp_path)
    given = pages(img)
    given[GEN + 5] = [body("and so on.", 60, 38), Img(100, str(img["a"]))]  # in no entry
    region, _, notes = run(given)
    assert [i.page for i in region.unclaimed] == [GEN + 5]
    assert _blocked(notes)


def test_an_entry_without_its_image_blocks_the_run(tmp_path: Path) -> None:
    given = pages(_images(tmp_path))
    given[GEN + 2] = []
    region, _, notes = run(given)
    assert region.errors == [f"chart 2: 0 chart-sized images on p{GEN + 1} or the next page"]
    assert _blocked(notes)


def test_a_chart_inside_a_verse_blocks_the_run(tmp_path: Path) -> None:
    given = pages(_images(tmp_path))
    given[GEN].append(body("and the verse goes on.", 540, 38))
    _, _, notes = run(given)
    assert notes.charts.mid_verse == ["chart 1 (GEN 1:2)"]
    assert _blocked(notes)


# -- the order at a shared spot ----------------------------------------------------------------

TOPIC_PAGES: Pages = {
    WBSA_PAGE: [
        T("MADE-UP FEATURE . . . INDEX", 54, 40, 15, blue=True, bold=True, link=WBSA_PAGE),
        T("Patience", 72, 38, blue=True, link=TOPIC),
    ],
    TOPIC: [
        T("What the Bible Says about", 63, 38, 15, blue=True, bold=True, link=WBSA_PAGE),
        T("patience", 57, 214, 23, bold=True),
        T("A MADE-UP SUBHEAD", 97, 38, 9, bold=True),
        T("Second made-up verse that runs on to", 107, 38, width=302),
        T("the end.", 122, 38, width=40),
        T("(", 150, 250, 9),
        T("Genesis 1:2", 150, 252, 9, blue=True, link=GEN),
        T(")", 150, 338, 9),
    ],
}


def test_a_chart_after_a_topic_at_one_verse_end_shows_after_it_and_moves_nothing(
    tmp_path: Path,
) -> None:
    given = {**pages(_images(tmp_path)), **TOPIC_PAGES}
    given[GEN].insert(-1, T("Patience", 200, 250, blue=True, bold=True, link=TOPIC))
    result, notes = run(given)[1:]
    no_charts = {n: [i for i in items if isinstance(i, T)] for n, items in given.items()}
    others = [n for n in notes.payload if n["type"] != "chart"]
    assert others == [n for n in run(no_charts)[2].payload]
    data, notes_dir = tmp_path / "data", tmp_path / "notes"
    data.mkdir()
    notes_dir.mkdir()
    (data / "EMB.json").write_text(json.dumps(translation_payload(result, "Rights.")), "utf-8")
    (notes_dir / "EMB.json").write_text(json.dumps(notes_payload(notes, "EMB")), "utf-8")
    assets = tmp_path / "assets"
    write_assets(assets / "EMB", notes.charts.assets)
    build_database(tmp_path / "bible.db", [data], notes_dirs=[notes_dir], assets_dirs=[assets])
    with sqlite3.connect(tmp_path / "bible.db") as conn:
        rows = conn.execute(
            "SELECT label, ordinal, image FROM translator_notes "
            "WHERE chapter = 1 AND verse = 2 ORDER BY ordinal, id"
        ).fetchall()
    assert rows == [("What the Bible Says About", 1, None), ("Chart", 2, "chart-01.jpg")]


# -- the asset files ---------------------------------------------------------------------------


def test_assets_are_written_as_given_and_a_stale_file_blocks_the_write(tmp_path: Path) -> None:
    images = {"chart-01.jpg": jpeg(20, 10), "chart-02.jpg": jpeg(10, 20)}
    folder = tmp_path / "assets" / "EMB"
    assert stale_assets(folder, images) == []  # no folder yet
    write_assets(folder, images)
    first = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert first == images
    write_assets(folder, images)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == first  # a re-run: identical
    (folder / "chart-03.jpg").write_bytes(jpeg())
    assert stale_assets(folder, images) == ["chart-03.jpg"]


# -- the EPUB witness --------------------------------------------------------------------------

CONTAINER = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
</rootfiles></container>"""
OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0"><manifest>
<item id="a" href="OEBPS/a.html" media-type="application/xhtml+xml"/>
<item id="b" href="OEBPS/b.html" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="a"/><itemref idref="b"/></spine></package>"""
CHAPTERS = """<html><body>
<p><big>Genesis</big> <big>1</big></p>
<p><sup>1</sup> A made-up first verse.</p>
<p><sup>2</sup> Second made-up verse that runs on to the end.</p>
<p><img src="one.jpg"/></p>
<p><sup>3</sup> A made-up third verse.</p>
<p><sup>4</sup> A made-up fourth verse.</p>
<p><big>Genesis</big> <big>2</big></p>
<p><sup>1</sup> Chapter two opens.</p>
<p><img src="three.jpg"/></p>
<p><sup>2</sup> It goes on.</p>
<p><img src="other.jpg"/></p>
<p><sup>3</sup> It ends.</p>
</body></html>"""
INDEX = """<html><body><p><b>CHARTS INDEX</b></p>
<p><a>A Made-up Chart</a><span> (<a>Gen. 1:1-2</a>)</span></p>
<p><span>s=0 &gt;Plim Vosk Drane</span><span> (Gen. 1:3)</span></p>
<p><a>Another Made-up</a><span> (<a>Gen. 1–2</a>)</span></p>
<p><b>PERSPECTIVES INDEX</b></p></body></html>"""


def test_the_epub_witnesses_each_charts_place_and_index_entry(tmp_path: Path) -> None:
    _, _, notes = run(pages(_images(tmp_path)))
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("content.opf", OPF)
        archive.writestr("OEBPS/a.html", CHAPTERS)
        archive.writestr("OEBPS/b.html", INDEX)
        archive.writestr("OEBPS/one.jpg", jpeg(566, 383))  # chart 1, re-encoded smaller
        archive.writestr("OEBPS/three.jpg", jpeg(566, 401) + b"\x00\x00")  # chart 3, padded
        archive.writestr("OEBPS/other.jpg", jpeg(500, 751))  # a full page, at no chart's place
    cross = cross_check_epub_charts(
        notes.charts.region.charts, notes.charts.spots, path, load_skeleton()
    )
    assert [row[2:] for row in cross.rows] == [
        ("agree", "at the same place"),
        ("visible EPUB damage", "not in the EPUB"),  # chart 2 is lost; its entry is damaged
        ("agree", "at the same place"),
    ]
    assert (cross.entries, cross.large, cross.open, cross.elsewhere) == (3, 3, 0, ["GEN 2:2"])


@pytest.mark.parametrize("damaged", [False, True])
def test_an_index_entry_the_epub_words_otherwise_is_open_unless_visibly_damaged(
    tmp_path: Path, damaged: bool
) -> None:
    _, _, notes = run(pages(_images(tmp_path)))
    title = "s=0 >Some Other Title" if damaged else "Some Other Title"
    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("content.opf", OPF)
        archive.writestr("OEBPS/a.html", CHAPTERS)
        archive.writestr(
            "OEBPS/b.html", INDEX.replace("A Made-up Chart", title.replace(">", "&gt;"))
        )
    rows: Sequence[tuple[str, str, str, str]] = cross_check_epub_charts(
        notes.charts.region.charts, notes.charts.spots, path, load_skeleton()
    ).rows
    assert rows[0][2] == ("visible EPUB damage" if damaged else "open")
