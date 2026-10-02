"""The /v1/topics* + /v1/verses/{ref}/topics endpoints against the synthetic corpus (fast).

Browse + q/section filters, detail (verse_count, see_also), topic→verses with include_text +
pagination, the reverse verse→topics lookup, the redirect (see_also, 0 verses) case, 404s,
400 unparseable ref, empty-200, and the immutable-ETag 304.

Synthetic topics (apikit): ANXIETY (→care redirect, 0 verses), CARE (GEN 1:1, JHN 3:16, 1JN 1:1),
CREATION (GEN 1:1-2), LOVE (JHN 3:16). No dependence on the real Nave's dataset.

ADR-0013 (a second, private source): ``source`` on every body, ``?source=``, ``sources``, the
400 ``unknown_source``, and the union across sources — against a copy of the corpus with two
made-up topics of a made-up source (``two_sources``), so the one-source expectations above stand.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from apikit import verse_text
from bible_api.app import create_app
from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

NAVES = "Nave's Topical Bible"
PRIVATE = "Made-up Finder"
SUMMARY_KEYS = ["id", "name", "section", "see_also", "source"]
PAGE_KEYS = ["q", "section", "limit", "offset", "total", "topics", "source", "sources"]


# --- browse + filters ----------------------------------------------------------------


def test_browse_default_order_and_echo(client: TestClient) -> None:
    body = client.get("/v1/topics").json()
    assert list(body.keys()) == PAGE_KEYS
    assert (body["q"], body["section"], body["source"]) == (None, None, None)
    assert (body["limit"], body["offset"], body["total"]) == (50, 0, 4)
    # Ordered by name: ANXIETY, CARE, CREATION, LOVE.
    assert [t["id"] for t in body["topics"]] == ["anxiety", "care", "creation", "love"]
    assert list(body["topics"][0].keys()) == SUMMARY_KEYS
    assert body["topics"][0]["source"] == NAVES
    assert body["sources"] == [{"source": NAVES, "total": 4}]


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
        "source": NAVES,
    }
    assert list(body.keys()) == [*SUMMARY_KEYS[:4], "verse_count", "source"]


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
    assert list(body.keys())[-2:] == ["verses", "source"] and body["source"] == NAVES
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
    assert [list(t.keys()) for t in body["topics"]] == [SUMMARY_KEYS, SUMMARY_KEYS]


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


# --- ADR-0013: two sources -------------------------------------------------------------


@pytest.fixture(scope="module")
def two_sources(db_path: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The corpus plus a made-up private source: "Care made up" (GEN 1:2, JHN 3:16) and a
    redirect, "Zeal made up" → vf-1. Mixed-case names sort after the all-capitals public names
    that share their first letter (binary order)."""
    path = tmp_path_factory.mktemp("two-sources") / "bible.db"
    shutil.copyfile(db_path, path)
    with sqlite3.connect(path) as conn:
        conn.executemany(
            "INSERT INTO topics (id, name, section, see_also, source) VALUES (?, ?, ?, ?, ?)",
            [
                ("vf-1", "Care made up", "C", None, PRIVATE),
                ("vf-2", "Zeal made up", "Z", "vf-1", PRIVATE),
            ],
        )
        conn.executemany(
            "INSERT INTO topic_verses (topic_id, book_id, chapter, verse) VALUES (?, ?, ?, ?)",
            [("vf-1", "GEN", 1, 2), ("vf-1", "JHN", 3, 16)],
        )
    app = create_app(db_path=path, enable_semantic=False)
    with TestClient(app) as test_client:
        yield test_client


def test_two_sources_browse_union_and_totals(two_sources: TestClient) -> None:
    body = two_sources.get("/v1/topics").json()
    assert list(body.keys()) == PAGE_KEYS
    assert [t["id"] for t in body["topics"]] == [
        "anxiety",
        "care",
        "creation",
        "vf-1",
        "love",
        "vf-2",
    ]
    assert body["sources"] == [{"source": PRIVATE, "total": 2}, {"source": NAVES, "total": 4}]
    assert sum(s["total"] for s in body["sources"]) == body["total"] == 6


def test_source_filter_pages_one_source(two_sources: TestClient, client: TestClient) -> None:
    body = two_sources.get("/v1/topics", params={"source": PRIVATE}).json()
    assert (body["source"], body["total"]) == (PRIVATE, 2)
    assert [(t["id"], t["source"]) for t in body["topics"]] == [
        ("vf-1", PRIVATE),
        ("vf-2", PRIVATE),
    ]
    # the facet ignores the source filter itself
    assert body["sources"] == [{"source": PRIVATE, "total": 2}, {"source": NAVES, "total": 4}]
    # Nave's alone pages exactly as a one-source build does
    naves = two_sources.get("/v1/topics", params={"source": f" {NAVES} ", "limit": 2}).json()
    plain = client.get("/v1/topics", params={"limit": 2}).json()
    assert naves["topics"] == plain["topics"] and naves["total"] == plain["total"] == 4
    assert naves["source"] == NAVES


def test_sources_honour_q_and_section(two_sources: TestClient) -> None:
    body = two_sources.get("/v1/topics", params={"section": "C"}).json()
    assert [t["id"] for t in body["topics"]] == ["care", "creation", "vf-1"]
    assert body["sources"] == [{"source": PRIVATE, "total": 1}, {"source": NAVES, "total": 2}]
    none = two_sources.get("/v1/topics", params={"q": "nothing-matches"}).json()
    assert none["total"] == 0
    assert none["sources"] == [{"source": PRIVATE, "total": 0}, {"source": NAVES, "total": 0}]
    combined = two_sources.get("/v1/topics", params={"section": "C", "source": PRIVATE}).json()
    assert [t["id"] for t in combined["topics"]] == ["vf-1"]


def test_unknown_source_400(two_sources: TestClient) -> None:
    resp = two_sources.get("/v1/topics", params={"source": "No Such Source"})
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "unknown_source"
    assert error["detail"] == {"source": "No Such Source", "available": [PRIVATE, NAVES]}
    # a blank filter is no filter
    assert two_sources.get("/v1/topics", params={"source": "  "}).json()["total"] == 6


def test_two_sources_detail_verses_and_reverse(two_sources: TestClient) -> None:
    detail = two_sources.get("/v1/topics/vf-2").json()
    assert (detail["see_also"], detail["verse_count"], detail["source"]) == ("vf-1", 0, PRIVATE)
    verses = two_sources.get("/v1/topics/vf-1/verses", params={"include_text": "false"}).json()
    assert verses["source"] == PRIVATE
    assert [(v["book"], v["verse"]) for v in verses["verses"]] == [("GEN", 2), ("JHN", 16)]
    reverse = two_sources.get("/v1/verses/John 3:16/topics").json()
    assert [(t["id"], t["source"]) for t in reverse["topics"]] == [
        ("care", NAVES),
        ("vf-1", PRIVATE),
        ("love", NAVES),
    ]
    assert reverse["total"] == 3


def test_source_filter_etag_304(two_sources: TestClient) -> None:
    resp = two_sources.get("/v1/topics", params={"source": PRIVATE})
    assert resp.headers["cache-control"] == CACHE_CONTROL
    again = two_sources.get(
        "/v1/topics", params={"source": PRIVATE}, headers={"If-None-Match": resp.headers["etag"]}
    )
    assert again.status_code == 304
