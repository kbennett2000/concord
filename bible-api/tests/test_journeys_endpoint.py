"""The forward /v1/journeys endpoints against the synthetic corpus (fast).

List + pagination/echo, detail with ordered stops resolving to real places (coords + the v3
honesty model for an unknown-place stop), the source/note one-reconstruction flag, 404 for an
unknown journey, and the immutable-ETag 304.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

SUMMARY_KEYS = ["id", "name", "scripture", "dating", "stop_count"]
STOP_KEYS = [
    "ordinal",
    "place_id",
    "name",
    "friendly_id",
    "latitude",
    "longitude",
    "confidence",
    "status",
    "reference",
]


# --- browse / list -------------------------------------------------------------------


def test_list_default_order_and_echo(client: TestClient) -> None:
    body = client.get("/v1/journeys").json()
    assert (body["limit"], body["offset"], body["total"]) == (50, 0, 2)
    # ordered by id: j_paul before j_wander
    assert [j["id"] for j in body["journeys"]] == ["j_paul", "j_wander"]


def test_summary_shape_and_stop_count(client: TestClient) -> None:
    body = client.get("/v1/journeys").json()
    paul = body["journeys"][0]
    assert list(paul.keys()) == SUMMARY_KEYS
    assert paul["stop_count"] == 4  # 4 stops incl. the p_ant1 revisit
    assert paul["dating"] == "c. AD 47 (test)"
    # null dating surfaced honestly
    assert body["journeys"][1]["dating"] is None


def test_list_pagination(client: TestClient) -> None:
    body = client.get("/v1/journeys", params={"limit": 1, "offset": 1}).json()
    assert body["total"] == 2  # total ignores the page window
    assert [j["id"] for j in body["journeys"]] == ["j_wander"]


# --- detail --------------------------------------------------------------------------


def test_detail_ordered_stops_and_honesty_fields(client: TestClient) -> None:
    body = client.get("/v1/journeys/j_paul").json()
    assert body["id"] == "j_paul"
    assert body["name"] == "Paul Test Journey"
    # the one-reconstruction flag: source + note both present
    assert body["source"] == "Acts (test)."
    assert body["note"].startswith("One proposed reconstruction")
    # ordered stops, with revisits preserved (p_ant1 at 2 & 3, p_jeru at 1 & 4)
    assert [(s["ordinal"], s["place_id"]) for s in body["stops"]] == [
        (1, "p_jeru"),
        (2, "p_ant1"),
        (3, "p_ant1"),
        (4, "p_jeru"),
    ]
    first = body["stops"][0]
    assert list(first.keys()) == STOP_KEYS
    # the stop resolves to its real place (coords + name from the join)
    assert (first["name"], first["latitude"], first["longitude"]) == ("Jerusalem", 31.78, 35.23)
    assert first["status"] == "identified"
    assert first["reference"] == "Acts 13:1"


def test_detail_stop_on_unknown_place_has_null_coords(client: TestClient) -> None:
    """The v3 honesty model rides along: a stop on an unknown place carries null coords."""
    body = client.get("/v1/journeys/j_wander").json()
    (stop,) = body["stops"]
    assert stop["place_id"] == "p_nod"
    assert stop["latitude"] is None
    assert stop["longitude"] is None
    assert stop["confidence"] is None
    assert stop["status"] == "unknown"


def test_detail_unknown_journey_404(client: TestClient) -> None:
    response = client.get("/v1/journeys/nope")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "unknown_journey"
    assert body["error"]["detail"] == {"journey_id": "nope"}


# --- reverse: /v1/places/{id}/journeys -----------------------------------------------


def test_reverse_lists_journeys_through_a_place(client: TestClient) -> None:
    body = client.get("/v1/places/p_ant1/journeys").json()
    assert body["id"] == "p_ant1"
    assert body["total"] == 1
    j = body["journeys"][0]
    assert (j["id"], j["stop_count"]) == ("j_paul", 4)
    assert list(j.keys()) == SUMMARY_KEYS


def test_reverse_dedups_a_revisited_place(client: TestClient) -> None:
    # p_jeru is visited twice by j_paul (ordinals 1 and 4) → one row, not two.
    body = client.get("/v1/places/p_jeru/journeys").json()
    assert [j["id"] for j in body["journeys"]] == ["j_paul"]
    assert body["total"] == 1


def test_reverse_unknown_place_stop_resolves(client: TestClient) -> None:
    # p_nod is an unknown place but still a real place row → its journey is listed.
    body = client.get("/v1/places/p_nod/journeys").json()
    assert [j["id"] for j in body["journeys"]] == ["j_wander"]


def test_reverse_real_place_in_no_journey_is_empty(client: TestClient) -> None:
    # p_ant2 exists but no journey passes through it → 200 with an empty list (not 404).
    response = client.get("/v1/places/p_ant2/journeys")
    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["total"], body["journeys"]) == ("p_ant2", 0, [])


def test_reverse_unknown_place_404(client: TestClient) -> None:
    response = client.get("/v1/places/nope/journeys")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_place"


# --- caching -------------------------------------------------------------------------


def test_immutable_etag_304(client: TestClient) -> None:
    for url in ("/v1/journeys", "/v1/journeys/j_paul", "/v1/places/p_ant1/journeys"):
        response = client.get(url)
        assert response.headers["cache-control"] == CACHE_CONTROL
        etag = response.headers["etag"]
        not_modified = client.get(url, headers={"If-None-Match": etag})
        assert not_modified.status_code == 304
        assert not_modified.content == b""
