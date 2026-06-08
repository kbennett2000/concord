"""Journeys loader behaviour on synthetic fixtures: journeys + ordered stops land, stops are
validated as FKs into the EXISTING places table (unknown place_id fails loud), structural
validation (duplicate id/ordinal, empty stops) fails loud, and rebuilds are idempotent. No
dependence on the real curated dataset; places come from synthetic geo via geokit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bible_core.loader import LoaderError, build_database
from bible_core.queries import get_journey, get_journey_stops
from geokit import ancient_place, assoc, modern_loc, verse_ref, write_geo
from loaderkit import book, chapter, translation, verse, write_translation


def _corpus(tmp_path: Path) -> Path:
    tdir = tmp_path / "translations"
    webx = translation(
        "WEBX",
        [book("Gen", 1, [chapter(1, [verse(1, "In the beginning."), verse(2, "The earth.")])])],
    )
    write_translation(tdir, webx)
    return tdir


def _geo(tmp_path: Path) -> Path:
    """Two real-enough places: an identified one with coords, and a coordinate-less unknown."""
    gdir = tmp_path / "geography"
    write_geo(
        gdir,
        [
            ancient_place(
                "a_ant",
                "Antioch",
                associations={"m1": assoc(1000, "Antakya")},
                verses=[verse_ref(1, 1, 1)],
            ),
            ancient_place("a_nod", "Nod", specials=("unknown_place",)),
        ],
        [modern_loc("m1", 36.16, 36.20)],
    )
    return gdir


def _journeys_payload() -> dict[str, object]:
    return {
        "journeys": [
            {
                "id": "trek",
                "name": "A Trek",
                "scripture": "Acts 13",
                "dating": "c. AD 47",
                "source": "Acts.",
                "note": "One proposed reconstruction.",
                "stops": [
                    {"ordinal": 1, "place_id": "a_ant", "reference": "Acts 13:1"},
                    {"ordinal": 2, "place_id": "a_nod"},  # no reference → optional
                    {"ordinal": 3, "place_id": "a_ant", "reference": "Acts 14:26"},  # revisit
                ],
            }
        ]
    }


def _build(tmp_path: Path, payload: dict[str, object]) -> tuple[Path, object]:
    jdir = tmp_path / "journeys"
    jdir.mkdir(parents=True)
    (jdir / "journeys.json").write_text(json.dumps(payload), encoding="utf-8")
    stats = build_database(
        tmp_path / "bible.db", [_corpus(tmp_path)], geo_dir=_geo(tmp_path), journeys_dir=jdir
    )
    return tmp_path / "bible.db", stats


def test_counts(tmp_path: Path) -> None:
    _, stats = _build(tmp_path, _journeys_payload())
    assert stats.journeys == 1  # type: ignore[attr-defined]
    assert stats.journey_stops == 3  # type: ignore[attr-defined]


def test_journey_and_ordered_stops_load(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _journeys_payload())
    import sqlite3

    conn = sqlite3.connect(db)
    journey = get_journey(conn, "trek")
    assert journey is not None
    assert journey.dating == "c. AD 47"
    stops = get_journey_stops(conn, "trek")
    assert [(s.ordinal, s.place_id) for s in stops] == [(1, "a_ant"), (2, "a_nod"), (3, "a_ant")]
    assert stops[1].reference is None  # optional reference omitted


def test_unknown_place_id_fails_loud(tmp_path: Path) -> None:
    payload = _journeys_payload()
    payload["journeys"][0]["stops"][1]["place_id"] = "a_ghost"  # type: ignore[index]
    with pytest.raises(LoaderError, match="unknown place_id 'a_ghost'"):
        _build(tmp_path, payload)


def test_duplicate_ordinal_fails_loud(tmp_path: Path) -> None:
    payload = _journeys_payload()
    payload["journeys"][0]["stops"][1]["ordinal"] = 1  # type: ignore[index]
    with pytest.raises(LoaderError, match="duplicate ordinal"):
        _build(tmp_path, payload)


def test_duplicate_journey_id_fails_loud(tmp_path: Path) -> None:
    payload = _journeys_payload()
    payload["journeys"].append(dict(payload["journeys"][0]))  # type: ignore[attr-defined,index]
    with pytest.raises(LoaderError, match="duplicate journey id 'trek'"):
        _build(tmp_path, payload)


def test_empty_stops_fails_loud(tmp_path: Path) -> None:
    payload = _journeys_payload()
    payload["journeys"][0]["stops"] = []  # type: ignore[index]
    with pytest.raises(LoaderError, match="'stops' must be a non-empty list"):
        _build(tmp_path, payload)


def test_no_journeys_dir_yields_zero(tmp_path: Path) -> None:
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])  # journeys_dir omitted
    assert stats.journeys == 0
    assert stats.journey_stops == 0


def test_build_is_idempotent(tmp_path: Path) -> None:
    payload = _journeys_payload()
    first = _build(tmp_path, payload)[1]
    second = build_database(
        tmp_path / "bible.db",
        [_corpus(tmp_path)],
        geo_dir=_geo(tmp_path),
        journeys_dir=tmp_path / "journeys",
    )
    assert (first.journeys, first.journey_stops) == (  # type: ignore[attr-defined]
        second.journeys,
        second.journey_stops,
    )
