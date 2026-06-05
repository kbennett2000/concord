"""The four /v1/places* endpoints against the synthetic corpus (fast).

Validation, response shapes, the honesty model (named lat/lon; null coords for unknown),
disambiguation, verse-text hydration, the inverse lookup, and the immutable-ETag 304.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from apikit import verse_text
from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

SUMMARY_KEYS = [
    "id",
    "friendly_id",
    "name",
    "type",
    "latitude",
    "longitude",
    "confidence",
    "confidence_score",
    "status",
]


# --- browse / list -------------------------------------------------------------------


def test_browse_default_order_and_echo(client: TestClient) -> None:
    body = client.get("/v1/places").json()
    assert (body["type"], body["status"], body["q"]) == (None, None, None)
    assert (body["limit"], body["offset"], body["total"]) == (50, 0, 4)
    # name asc, id asc: the two Antiochs, then Jerusalem, then Nod
    assert [p["id"] for p in body["places"]] == ["p_ant1", "p_ant2", "p_jeru", "p_nod"]


def test_summary_key_order(client: TestClient) -> None:
    body = client.get("/v1/places").json()
    assert list(body["places"][0].keys()) == SUMMARY_KEYS


def test_filter_type(client: TestClient) -> None:
    body = client.get("/v1/places", params={"type": "region"}).json()
    assert [p["id"] for p in body["places"]] == ["p_nod"]
    assert body["type"] == "region"


def test_filter_status(client: TestClient) -> None:
    body = client.get("/v1/places", params={"status": "disputed"}).json()
    assert [p["id"] for p in body["places"]] == ["p_ant2"]


def test_q_substring_disambiguation(client: TestClient) -> None:
    body = client.get("/v1/places", params={"q": "antioch"}).json()
    ids = [p["id"] for p in body["places"]]
    assert ids == ["p_ant1", "p_ant2"]  # two distinct ids sharing name "Antioch"
    assert {p["name"] for p in body["places"]} == {"Antioch"}


def test_pagination(client: TestClient) -> None:
    body = client.get("/v1/places", params={"limit": 2, "offset": 1}).json()
    assert body["total"] == 4
    assert [p["id"] for p in body["places"]] == ["p_ant2", "p_jeru"]


def test_unknown_type_400(client: TestClient) -> None:
    response = client.get("/v1/places", params={"type": "nope"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "unknown_type"
    assert body["error"]["detail"]["type"] == "nope"
    assert "settlement" in body["error"]["detail"]["available"]


def test_unknown_status_400(client: TestClient) -> None:
    response = client.get("/v1/places", params={"status": "nope"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_status"


def test_bad_pagination_422(client: TestClient) -> None:
    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        response = client.get("/v1/places", params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_parameter"


# --- detail --------------------------------------------------------------------------


def test_detail_full_shape(client: TestClient) -> None:
    body = client.get("/v1/places/p_jeru").json()
    assert body == {
        "id": "p_jeru",
        "friendly_id": "Jerusalem",
        "name": "Jerusalem",
        "url_slug": "jerusalem",
        "type": "settlement",
        "preceding_article": "",
        "latitude": 31.78,  # named lat/lon — never an ordered pair
        "longitude": 35.23,
        "confidence": "high",
        "confidence_score": 1000,
        "status": "identified",
        "modern_name": "Jerusalem",
        "verse_count": 3,
    }


def test_detail_unknown_404(client: TestClient) -> None:
    response = client.get("/v1/places/nope")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "unknown_place"
    assert body["error"]["detail"]["place_id"] == "nope"


def test_honesty_unknown_place_null_coords(client: TestClient) -> None:
    body = client.get("/v1/places/p_nod").json()
    assert (body["latitude"], body["longitude"], body["confidence"]) == (None, None, None)
    assert (body["confidence_score"], body["status"]) == (None, "unknown")


def test_honesty_disputed_keeps_coords(client: TestClient) -> None:
    body = client.get("/v1/places/p_ant2").json()
    assert body["status"] == "disputed"
    assert (body["latitude"], body["longitude"], body["confidence"]) == (38.30, 31.18, "medium")


# --- place → verses (hydration) ------------------------------------------------------


def test_place_verses_hydrate_and_order(client: TestClient) -> None:
    body = client.get("/v1/places/p_jeru/verses", params={"translation": "KJV"}).json()
    assert (body["id"], body["translation"], body["include_text"]) == ("p_jeru", "KJV", True)
    assert body["total"] == 3
    # canonical order: GEN 1:1, GEN 1:2, JHN 3:16
    assert [(v["book"], v["chapter"], v["verse"]) for v in body["verses"]] == [
        ("GEN", 1, 1),
        ("GEN", 1, 2),
        ("JHN", 3, 16),
    ]
    assert body["verses"][0]["reference"] == "Genesis 1:1"
    assert body["verses"][0]["text"] == verse_text("GEN", 1, 1, "KJV")


def test_place_verses_include_text_false(client: TestClient) -> None:
    body = client.get("/v1/places/p_jeru/verses", params={"include_text": "false"}).json()
    assert body["translation"] is None and body["include_text"] is False
    assert all(v["text"] is None for v in body["verses"])


def test_place_verses_null_when_translation_omits(client: TestClient) -> None:
    # WEB omits JHN 3:16 → its text is null, but the verse still appears.
    body = client.get("/v1/places/p_jeru/verses", params={"translation": "WEB"}).json()
    jhn = next(v for v in body["verses"] if v["book"] == "JHN")
    assert jhn["text"] is None


def test_place_verses_unknown_404(client: TestClient) -> None:
    response = client.get("/v1/places/nope/verses")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_place"


# --- verse → places (inverse) --------------------------------------------------------


def test_verse_places_for_reference(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:16/places").json()
    assert body["reference"] == "John 3:16"
    assert [p["id"] for p in body["places"]] == ["p_jeru"]
    assert body["total"] == 1


def test_verse_places_range_union(client: TestClient) -> None:
    # Genesis 1 names Jerusalem (1:1 + 1:2 → one row, deduped)
    body = client.get("/v1/verses/Genesis 1/places").json()
    assert [p["id"] for p in body["places"]] == ["p_jeru"]
    assert body["total"] == 1


def test_verse_places_empty_list(client: TestClient) -> None:
    response = client.get("/v1/verses/John 3:17/places")  # a placeless verse
    assert response.status_code == 200
    assert response.json()["places"] == []


def test_verse_places_unparsable_400(client: TestClient) -> None:
    response = client.get("/v1/verses/foo bar/places")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unparseable_reference"


def test_bidirectional_round_trip(client: TestClient) -> None:
    # place → verses lists JHN 3:16; verse → places lists that place back.
    refs = client.get("/v1/places/p_jeru/verses", params={"include_text": "false"}).json()
    assert ("JHN", 3, 16) in [(v["book"], v["chapter"], v["verse"]) for v in refs["verses"]]
    back = client.get("/v1/verses/John 3:16/places").json()
    assert "p_jeru" in [p["id"] for p in back["places"]]


# --- caching -------------------------------------------------------------------------


def test_immutable_etag_304_all_endpoints(client: TestClient) -> None:
    for url in (
        "/v1/places",
        "/v1/places/p_jeru",
        "/v1/places/p_jeru/verses",
        "/v1/verses/John 3:16/places",
    ):
        response = client.get(url)
        assert response.headers["cache-control"] == CACHE_CONTROL
        etag = response.headers["etag"]
        not_modified = client.get(url, headers={"If-None-Match": etag})
        assert not_modified.status_code == 304
        assert not_modified.content == b""


def test_healthz_place_count(client: TestClient) -> None:
    assert client.get("/healthz").json()["place_count"] == 4
