"""Integration: build from the real committed journeys + geography data and check reality.

Excluded from the default run (``-m "not integration"``); run with ``pytest -m integration``.
Pins Paul's first journey against the frozen committed data: the ordered stops, the
disambiguation foundation (start/return Syrian Antioch is a different place-id than the
Pisidian-Antioch stop), and that every stop resolves to a real place with coordinates.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import build_database
from bible_core.queries import (
    get_journey,
    get_journey_stops,
    get_journeys_for_place,
    list_journeys,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"
GEOGRAPHY = REPO_ROOT / "data" / "geography"
JOURNEYS = REPO_ROOT / "data" / "journeys"


def _build(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "bible.db"
    build_database(db, [TRANSLATIONS], geo_dir=GEOGRAPHY, journeys_dir=JOURNEYS)
    return sqlite3.connect(db)


def test_paul_first_loads_with_ordered_stops(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    journey = get_journey(conn, "paul-first")
    assert journey is not None
    assert journey.name == "Paul's First Missionary Journey"
    assert journey.dating is not None  # dated as a whole
    assert journey.source and journey.note  # honesty: one reconstruction + its source

    stops = get_journey_stops(conn, "paul-first")
    assert [s.ordinal for s in stops] == list(range(1, 16))  # 15 contiguous stops
    # The start and the return are the SAME place (Syrian Antioch) — a revisited place-id.
    assert stops[0].place_id == stops[-1].place_id == "ae41ab4"


def test_antioch_disambiguation_holds(tmp_path: Path) -> None:
    """The start/return Antioch (on the Orontes) is a different place than the mid-journey
    Antioch in Pisidia — the v3 disambiguation foundation, referenced not rebuilt."""
    conn = _build(tmp_path)
    stops = get_journey_stops(conn, "paul-first")
    place_ids = [s.place_id for s in stops]
    assert "ae41ab4" in place_ids  # Antioch on the Orontes (Syrian)
    assert "a6c704a" in place_ids  # Antioch in Pisidia
    assert "ae41ab4" != "a6c704a"


def test_every_stop_resolves_to_a_real_place_with_coords(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    stops = get_journey_stops(conn, "paul-first")
    for s in stops:
        # the LEFT JOIN found the place (FK held) and it's an identified settlement with coords
        assert s.name is not None, f"stop {s.ordinal} ({s.place_id}) did not resolve to a place"
        assert s.latitude is not None and s.longitude is not None
        assert s.status == "identified"


def test_reverse_lists_journeys_for_a_stop(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    # Syrian Antioch starts the first three journeys → all three listed, ordered by id.
    shared = get_journeys_for_place(conn, "ae41ab4")
    assert [j.id for j in shared] == ["paul-first", "paul-second", "paul-third"]
    # Paphos is unique to the first journey.
    paphos = get_journeys_for_place(conn, "a314765")
    assert [j.id for j in paphos] == ["paul-first"]
    assert paphos[0].stop_count == 15


def test_curated_set_loaded(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    page = list_journeys(conn, 50, 0)
    assert page.total == 5
    assert [j.id for j in page.rows] == [
        "exodus",
        "paul-first",
        "paul-rome",
        "paul-second",
        "paul-third",
    ]


def test_exodus_honesty_model(tmp_path: Path) -> None:
    """The Exodus is one proposed reconstruction with a debated whole-journey dating, and many
    of its wilderness stations are tentatively identified — surfaced via confidence, not hidden."""
    conn = _build(tmp_path)
    journey = get_journey(conn, "exodus")
    assert journey is not None
    assert journey.dating is not None
    assert "debated" in journey.dating.lower()  # whole-journey dating is hedged, not faked
    stops = get_journey_stops(conn, "exodus")
    assert len(stops) == 15
    # every stop resolves to a real place (FK held)
    assert all(s.name is not None for s in stops)
    # the honesty model is genuinely exercised: at least one station carries low/medium confidence
    assert any(s.confidence in ("low", "medium") for s in stops)
