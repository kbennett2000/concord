"""The /v1/topics* + /v1/verses/{ref}/topics endpoints against the synthetic corpus (fast).

Browse + q/section filters, detail (verse_count, see_also), topic→verses with include_text +
pagination, the reverse verse→topics lookup, the redirect (see_also, 0 verses) case, 404s,
400 unparseable ref, empty-200, and the immutable-ETag 304.

Synthetic topics (apikit): ANXIETY (→care redirect, 0 verses), CARE (GEN 1:1, JHN 3:16, 1JN 1:1),
CREATION (GEN 1:1-2), LOVE (JHN 3:16). No dependence on the real Nave's dataset.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from apikit import verse_text
from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

SUMMARY_KEYS = ["id", "name", "section", "see_also"]


# --- browse + filters ----------------------------------------------------------------


def test_browse_default_order_and_echo(client: TestClient) -> None:
    body = client.get("/v1/topics").json()
    assert (body["q"], body["section"]) == (None, None)
    assert (body["limit"], body["offset"], body["total"]) == (50, 0, 4)
    # Ordered by name: ANXIETY, CARE, CREATION, LOVE.
    assert [t["id"] for t in body["topics"]] == ["anxiety", "care", "creation", "love"]
    assert list(body["topics"][0].keys()) == SUMMARY_KEYS


def test_filter_q(client: TestClient) -> None:
    body = client.get("/v1/topics", params={"q": "care"}).json()
    assert [t["id"] for t in body["topics"]] == ["care"]
    assert body["q"] == "care"


def test_filter_q_case_insensitive(client: TestClient) -> None:
    assert client.get("/v1/topics", params={"q": "ANXI"}).json()["total"] == 1


def test_filter_section(client: TestClient) -> None:
    body = client.get("/v1/topics", params={"section": "C"}).json()
    assert [t["id"] for t in body["topics"]] == ["care", "creation"]


def test_pagination_non_overlapping(client: TestClient) -> None:
    p1 = client.get("/v1/topics", params={"limit": 2, "offset": 0}).json()
    p2 = client.get("/v1/topics", params={"limit": 2, "offset": 2}).json()
    assert p1["total"] == 4
    assert {t["id"] for t in p1["topics"]}.isdisjoint({t["id"] for t in p2["topics"]})


# --- detail --------------------------------------------------------------------------


def test_detail_full_shape(client: TestClient) -> None:
    body = client.get("/v1/topics/care").json()
    assert body == {
        "id": "care",
        "name": "CARE",
        "section": "C",
        "see_also": None,
        "verse_count": 3,
    }


def test_detail_redirect_see_also_zero_verses(client: TestClient) -> None:
    body = client.get("/v1/topics/anxiety").json()
    assert body["see_also"] == "care"
    assert body["verse_count"] == 0


def test_detail_unknown_404(client: TestClient) -> None:
    resp = client.get("/v1/topics/nope")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "unknown_topic"
    assert body["error"]["detail"]["topic_id"] == "nope"


# --- topic → verses ------------------------------------------------------------------


def test_topic_verses_hydrate_and_order(client: TestClient) -> None:
    body = client.get("/v1/topics/care/verses", params={"translation": "KJV"}).json()
    assert (body["id"], body["translation"], body["include_text"]) == ("care", "KJV", True)
    assert body["total"] == 3
    # Canonical order: GEN, JHN, 1JN.
    assert [(v["book"], v["chapter"], v["verse"]) for v in body["verses"]] == [
        ("GEN", 1, 1),
        ("JHN", 3, 16),
        ("1JN", 1, 1),
    ]
    assert body["verses"][0]["text"] == verse_text("GEN", 1, 1, "KJV")


def test_topic_verses_missing_verse_text_is_null(client: TestClient) -> None:
    # WEB omits JHN 3:16 → hydrated text is null, not an error.
    body = client.get("/v1/topics/care/verses", params={"translation": "WEB"}).json()
    jhn = next(v for v in body["verses"] if v["book"] == "JHN")
    assert jhn["text"] is None


def test_topic_verses_include_text_false(client: TestClient) -> None:
    body = client.get("/v1/topics/care/verses", params={"include_text": "false"}).json()
    assert body["translation"] is None and body["include_text"] is False
    assert all(v["text"] is None for v in body["verses"])


def test_redirect_topic_verses_empty(client: TestClient) -> None:
    body = client.get("/v1/topics/anxiety/verses").json()
    assert (body["total"], body["verses"]) == (0, [])


def test_topic_verses_unknown_404(client: TestClient) -> None:
    assert client.get("/v1/topics/nope/verses").status_code == 404


# --- reverse: verse → topics ---------------------------------------------------------


def test_verse_topics_for_reference(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:16/topics").json()
    assert body["reference"] == "John 3:16"
    # CARE and LOVE both cite JHN 3:16; ordered by name.
    assert [t["id"] for t in body["topics"]] == ["care", "love"]
    assert body["total"] == 2


def test_verse_topics_range_union(client: TestClient) -> None:
    # GEN 1:1-2 → CARE (1:1) + CREATION (1:1, 1:2), deduped, ordered by name.
    body = client.get("/v1/verses/Genesis 1:1-2/topics").json()
    assert [t["id"] for t in body["topics"]] == ["care", "creation"]


def test_verse_topics_empty_list(client: TestClient) -> None:
    resp = client.get("/v1/verses/John 4:1/topics")
    assert resp.status_code == 200
    assert resp.json()["topics"] == []


def test_verse_topics_unparsable_400(client: TestClient) -> None:
    resp = client.get("/v1/verses/foo bar/topics")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unparseable_reference"


def test_verse_topics_unknown_book_404(client: TestClient) -> None:
    resp = client.get("/v1/verses/Hezekiah 1:1/topics")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "unknown_book"


# --- caching -------------------------------------------------------------------------


def test_immutable_etag_304_all_endpoints(client: TestClient) -> None:
    for url in (
        "/v1/topics",
        "/v1/topics/care",
        "/v1/topics/care/verses",
        "/v1/verses/John 3:16/topics",
    ):
        resp = client.get(url)
        assert resp.headers["cache-control"] == CACHE_CONTROL
        etag = resp.headers["etag"]
        not_modified = client.get(url, headers={"If-None-Match": etag})
        assert not_modified.status_code == 304
        assert not_modified.content == b""
