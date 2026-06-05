"""Place read queries: filters, lookup, verse listing, and the inverse reference→places."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bible_core.parser import parse_reference
from bible_core.queries import (
    count_place_verses,
    distinct_place_types,
    get_place,
    get_place_verses,
    get_places_for_reference,
    list_places,
)
from bible_core.resolver import SqliteBookResolver
from bible_core.schema import create_schema
from bible_core.seed import seed_books

# (id, friendly_id, name, slug, type, article, lat, lon, conf, score, status, modern)
PLACES = [
    (
        "p_jeru",
        "Jerusalem",
        "Jerusalem",
        "jerusalem",
        "settlement",
        "",
        31.78,
        35.23,
        "high",
        1000,
        "identified",
        "Jerusalem",
    ),
    ("p_nod", "Nod", "Nod", "nod", "region", "", None, None, None, None, "unknown", None),
    (
        "p_ant1",
        "Antioch 1",
        "Antioch",
        "antioch-1",
        "settlement",
        "",
        36.20,
        36.16,
        "high",
        900,
        "identified",
        "Antakya",
    ),
    (
        "p_ant2",
        "Antioch 2",
        "Antioch",
        "antioch-2",
        "settlement",
        "",
        38.30,
        31.18,
        "medium",
        300,
        "disputed",
        "Yalvaç",
    ),
]
# (place_id, book_id, chapter, verse)
LINKS = [
    ("p_jeru", "GEN", 1, 1),
    ("p_jeru", "GEN", 1, 2),  # second GEN-1 verse → exercises dedup in a chapter range
    ("p_jeru", "JHN", 3, 16),
    ("p_nod", "GEN", 4, 16),
    ("p_ant1", "ACT", 11, 26),
    ("p_ant2", "ACT", 13, 14),
]


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "geo.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    seed_books(conn)
    conn.executemany(
        "INSERT INTO places (id, friendly_id, name, url_slug, type, preceding_article, "
        "latitude, longitude, confidence, confidence_score, status, modern_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        PLACES,
    )
    conn.executemany(
        "INSERT INTO place_verses (place_id, book_id, chapter, verse) VALUES (?, ?, ?, ?)",
        LINKS,
    )
    conn.commit()
    return conn


def test_list_places_default_order(tmp_path: Path) -> None:
    page = list_places(_db(tmp_path), None, None, None, 50, 0)
    assert page.total == 4
    # name asc, id asc tiebreak: the two Antiochs (p_ant1 then p_ant2), Jerusalem, Nod
    assert [p.id for p in page.rows] == ["p_ant1", "p_ant2", "p_jeru", "p_nod"]


def test_list_places_filters_and_substring(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    assert [p.id for p in list_places(conn, "region", None, None, 50, 0).rows] == ["p_nod"]
    assert [p.id for p in list_places(conn, None, "disputed", None, 50, 0).rows] == ["p_ant2"]
    antiochs = list_places(conn, None, None, "anti", 50, 0)  # case-insensitive substring
    assert [p.id for p in antiochs.rows] == ["p_ant1", "p_ant2"]
    assert antiochs.total == 2


def test_list_places_pagination(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    page = list_places(conn, None, None, None, 2, 1)
    assert page.total == 4  # total ignores limit/offset
    assert [p.id for p in page.rows] == ["p_ant2", "p_jeru"]


def test_get_place_hit_and_miss(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    jeru = get_place(conn, "p_jeru")
    assert jeru is not None
    assert (jeru.name, jeru.latitude, jeru.longitude, jeru.status) == (
        "Jerusalem",
        31.78,
        35.23,
        "identified",
    )
    nod = get_place(conn, "p_nod")
    assert nod is not None and nod.latitude is None and nod.confidence is None
    assert get_place(conn, "nope") is None


def test_place_verses_order_and_count(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    assert count_place_verses(conn, "p_jeru") == 3
    rows, total = get_place_verses(conn, "p_jeru", 50, 0)
    assert total == 3
    # canonical order: GEN (1) before JHN (43)
    assert [(r.book_id, r.chapter, r.verse) for r in rows] == [
        ("GEN", 1, 1),
        ("GEN", 1, 2),
        ("JHN", 3, 16),
    ]
    assert rows[0].book_name == "Genesis"


def test_places_for_reference_single_verse(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    ref = parse_reference("John 3:16", SqliteBookResolver(conn))
    page = get_places_for_reference(conn, ref)
    assert [p.id for p in page.rows] == ["p_jeru"]
    assert page.total == 1


def test_places_for_reference_range_union_dedup(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    # Genesis 1-4 covers Jerusalem (1:1 + 1:2 → deduped to one row) and Nod (4:16)
    ref = parse_reference("Genesis 1-4", SqliteBookResolver(conn))
    page = get_places_for_reference(conn, ref)
    assert [p.id for p in page.rows] == ["p_jeru", "p_nod"]  # name order; Jerusalem once
    assert page.total == 2


def test_places_for_reference_empty(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    ref = parse_reference("John 9:1", SqliteBookResolver(conn))  # no place there
    page = get_places_for_reference(conn, ref)
    assert page.rows == () and page.total == 0


def test_distinct_place_types(tmp_path: Path) -> None:
    assert distinct_place_types(_db(tmp_path)) == ["region", "settlement"]
