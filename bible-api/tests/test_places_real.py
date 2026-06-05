"""Integration: /v1/places* against a real bible.db (translations + geography).

Excluded from the default run (``-m "not integration"``). Pins the honesty model against the
real data — Jerusalem identified (named lat/lon in the right hemisphere) vs Nod/Eden unknown
(null coords) — plus disambiguation, hydration, the inverse lookup, and the ETag round-trip.
``enable_semantic=False`` keeps this test free of the embedding model.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from bible_api.app import create_app
from bible_api.errors import CACHE_CONTROL
from bible_core.loader import build_database
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"
GEOGRAPHY = REPO_ROOT / "data" / "geography"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    db_path = tmp_path_factory.mktemp("geo") / "bible.db"
    stats = build_database(db_path, [TRANSLATIONS], geo_dir=GEOGRAPHY)
    assert stats.places == 1340
    with TestClient(create_app(db_path=db_path, enable_semantic=False)) as test_client:
        yield test_client


def test_healthz_place_count(client: TestClient) -> None:
    assert client.get("/healthz").json()["place_count"] == 1340


def test_jerusalem_identified_with_named_coords(client: TestClient) -> None:
    body = client.get("/v1/places/a15257a").json()
    assert (body["friendly_id"], body["status"], body["confidence"]) == (
        "Jerusalem",
        "identified",
        "high",
    )
    assert round(body["latitude"], 2) == 31.78  # named lat (lonlat parts[1])
    assert round(body["longitude"], 2) == 35.23  # named lon (lonlat parts[0]) — right hemisphere
    assert body["verse_count"] == 955


@pytest.mark.parametrize("place_id", ["a1ad8e1", "af3daeb"])  # Nod, Eden 1
def test_unknown_places_have_null_coords(client: TestClient, place_id: str) -> None:
    body = client.get(f"/v1/places/{place_id}").json()
    assert (body["latitude"], body["longitude"], body["confidence"]) == (None, None, None)
    assert body["status"] == "unknown"


def test_disambiguation_distinct_ids(client: TestClient) -> None:
    body = client.get("/v1/places", params={"q": "Antioch"}).json()
    ids = {p["id"] for p in body["places"]}
    assert {"ae41ab4", "a6c704a"} <= ids  # two distinct Antiochs, distinct ids


def test_filters(client: TestClient) -> None:
    settlements = client.get("/v1/places", params={"type": "settlement", "limit": 5}).json()
    assert len(settlements["places"]) == 5
    assert all(p["type"] == "settlement" for p in settlements["places"])
    assert settlements["total"] == 843  # 844 ancient settlements − 1 excluded not_a_place
    unknowns = client.get("/v1/places", params={"status": "unknown"}).json()
    assert all(p["latitude"] is None and p["status"] == "unknown" for p in unknowns["places"])


def test_place_verses_hydration(client: TestClient) -> None:
    body = client.get("/v1/places/a15257a/verses", params={"translation": "KJV", "limit": 5}).json()
    assert body["translation"] == "KJV" and body["total"] == 955
    assert len(body["verses"]) == 5
    assert all(v["text"] for v in body["verses"])  # real KJV text hydrated
    assert all(" " in v["reference"] and ":" in v["reference"] for v in body["verses"])

    plain = client.get("/v1/places/a15257a/verses", params={"include_text": "false"}).json()
    assert plain["translation"] is None
    assert all(v["text"] is None for v in plain["verses"])


def test_verse_places_inverse_and_empty(client: TestClient) -> None:
    eden = client.get("/v1/verses/Genesis 2:8/places").json()
    assert eden["reference"] == "Genesis 2:8"
    assert "af3daeb" in [p["id"] for p in eden["places"]]  # Eden named in Gen 2:8

    empty = client.get("/v1/verses/Genesis 1:1/places")  # no place named there
    assert empty.status_code == 200
    assert empty.json()["places"] == []


def test_unknown_place_404(client: TestClient) -> None:
    response = client.get("/v1/places/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_place"


def test_etag_round_trip(client: TestClient) -> None:
    response = client.get("/v1/places/a15257a")
    assert response.headers["cache-control"] == CACHE_CONTROL
    etag = response.headers["etag"]
    not_modified = client.get("/v1/places/a15257a", headers={"If-None-Match": etag})
    assert not_modified.status_code == 304 and not_modified.content == b""
