"""Journey read queries: list + pagination, detail lookup, ordered stops joined to places
(coords/status surfaced honestly), the reverse place→journeys, and stop counts. Seeds tables
directly — no build, no dependence on the real curated dataset."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bible_core.queries import (
    count_journey_stops,
    get_journey,
    get_journey_stops,
    get_journeys_for_place,
    list_journeys,
)
from bible_core.schema import create_schema
from bible_core.seed import seed_books

# (id, friendly_id, name, slug, type, article, lat, lon, conf, score, status, modern)
PLACES = [
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
        "p_paph",
        "Paphos",
        "Paphos",
        "paphos",
        "settlement",
        "",
        34.75,
        32.41,
        "high",
        1000,
        "identified",
        "New Paphos",
    ),
    # A coordinate-less place (the honesty model) — a stop can point here; it just can't be pinned.
    ("p_nod", "Nod", "Nod", "nod", "region", "", None, None, None, None, "unknown", None),
]
# (id, name, scripture, dating, source, note)
JOURNEYS = [
    ("paul-first", "Paul's First Missionary Journey", "Acts 13–14", "c. AD 46–48", "Acts.", "One."),
    ("wanderings", "A Wandering", "Genesis 4", None, "Genesis.", "One."),  # null dating
]
# (journey_id, ordinal, place_id, reference)
STOPS = [
    ("paul-first", 1, "p_ant1", "Acts 13:1"),
    ("paul-first", 2, "p_paph", "Acts 13:6"),
    ("paul-first", 3, "p_ant1", "Acts 14:26"),  # return leg revisits Antioch
    ("wanderings", 1, "p_nod", "Genesis 4:16"),  # stop on a coordinate-less place
]


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "j.db")
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
        "INSERT INTO journeys (id, name, scripture, dating, source, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        JOURNEYS,
    )
    conn.executemany(
        "INSERT INTO journey_stops (journey_id, ordinal, place_id, reference) VALUES (?, ?, ?, ?)",
        STOPS,
    )
    conn.commit()
    return conn


def test_list_journeys_order_and_counts(tmp_path: Path) -> None:
    page = list_journeys(_db(tmp_path), 50, 0)
    assert page.total == 2
    # Ordered by id: "paul-first" before "wanderings".
    assert [j.id for j in page.rows] == ["paul-first", "wanderings"]
    paul = page.rows[0]
    assert paul.stop_count == 3
    assert paul.dating == "c. AD 46–48"
    assert page.rows[1].dating is None  # null dating surfaced honestly


def test_list_journeys_pagination(tmp_path: Path) -> None:
    page = list_journeys(_db(tmp_path), 1, 1)
    assert page.total == 2  # total ignores the page window
    assert [j.id for j in page.rows] == ["wanderings"]


def test_get_journey_full_metadata(tmp_path: Path) -> None:
    journey = get_journey(_db(tmp_path), "paul-first")
    assert journey is not None
    assert journey.name == "Paul's First Missionary Journey"
    assert journey.source == "Acts."
    assert journey.note == "One."


def test_get_journey_unknown_is_none(tmp_path: Path) -> None:
    assert get_journey(_db(tmp_path), "nope") is None


def test_get_journey_stops_ordered_with_place_join(tmp_path: Path) -> None:
    stops = get_journey_stops(_db(tmp_path), "paul-first")
    assert [s.ordinal for s in stops] == [1, 2, 3]
    assert [s.place_id for s in stops] == ["p_ant1", "p_paph", "p_ant1"]
    first = stops[0]
    assert first.friendly_id == "Antioch 1"
    assert first.name == "Antioch"
    assert first.latitude == 36.20
    assert first.status == "identified"
    assert first.reference == "Acts 13:1"


def test_stop_on_unknown_place_has_null_coords(tmp_path: Path) -> None:
    (stop,) = get_journey_stops(_db(tmp_path), "wanderings")
    assert stop.place_id == "p_nod"
    assert stop.latitude is None
    assert stop.longitude is None
    assert stop.confidence is None
    assert stop.status == "unknown"


def test_count_journey_stops(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    assert count_journey_stops(conn, "paul-first") == 3
    assert count_journey_stops(conn, "wanderings") == 1


def test_reverse_place_to_journeys_dedups_revisits(tmp_path: Path) -> None:
    # p_ant1 is visited twice by paul-first (ordinals 1 and 3) → one row, not two.
    rows = get_journeys_for_place(_db(tmp_path), "p_ant1")
    assert [j.id for j in rows] == ["paul-first"]
    assert rows[0].stop_count == 3


def test_reverse_place_in_no_journey_is_empty(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    assert get_journeys_for_place(conn, "p_paph") != ()  # Paphos is in paul-first
    assert get_journeys_for_place(conn, "p_unused") == ()  # absent place → empty
