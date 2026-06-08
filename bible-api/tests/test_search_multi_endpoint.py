"""/v1/search multi-translation mode (v5-S2, ADR-0003) + the contract-unchanged proof.

The additive ?translations= widening: single-translation mode must be byte-for-byte the pre-S2
response (no new keys reach the wire); multi mode dedups by canonical verse and carries the
per-translation matches map. Synthetic corpus (KJV/WEB/YLT, "GEN 1:1 (KJV)" text; WEB omits
JHN 3:16).
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

RESPONSE_KEYS = {"query", "translation", "book", "limit", "offset", "total", "hits"}
HIT_KEYS = {"book", "chapter", "verse", "reference", "snippet"}


# --- contract-unchanged proof (load-bearing) -----------------------------------------


def test_single_mode_is_additive_free(client: TestClient) -> None:
    """?translations= absent → no new field reaches the bytes; legacy shape exactly."""
    resp = client.get("/v1/search", params={"q": "gen", "translation": "KJV"})
    assert resp.status_code == 200
    assert b"matches" not in resp.content
    assert b"translations" not in resp.content
    body = resp.json()
    assert set(body.keys()) == RESPONSE_KEYS
    assert all(set(hit.keys()) == HIT_KEYS for hit in body["hits"])
    assert body["book"] is None  # the existing nullable field is still present as null


def test_default_translation_single_mode_unchanged(client: TestClient) -> None:
    resp = client.get("/v1/search", params={"q": "gen"})
    assert b"matches" not in resp.content and b"translations" not in resp.content
    assert set(resp.json().keys()) == RESPONSE_KEYS


def test_blank_translations_is_single_mode(client: TestClient) -> None:
    resp = client.get("/v1/search", params={"q": "gen", "translations": ""})
    assert b"matches" not in resp.content and b"translations" not in resp.content
    assert set(resp.json().keys()) == RESPONSE_KEYS


# --- multi mode: dedup + matches map -------------------------------------------------


def test_multi_dedup_and_matches_map(client: TestClient) -> None:
    body = client.get(
        "/v1/search", params={"q": "gen", "translations": "KJV,YLT", "book": "genesis"}
    ).json()
    assert body["total"] == 3  # GEN 1:1-3, each once
    keys = [(h["book"], h["chapter"], h["verse"]) for h in body["hits"]]
    assert keys == [("GEN", 1, 1), ("GEN", 1, 2), ("GEN", 1, 3)]
    for hit in body["hits"]:
        assert set(hit["matches"].keys()) == {"KJV", "YLT"}
        assert "<mark>GEN</mark>" in hit["matches"]["KJV"]  # snippet preserves source case


def test_flat_snippet_is_top_ranked_translation(client: TestClient) -> None:
    body = client.get(
        "/v1/search", params={"q": "gen", "translations": "KJV,YLT", "book": "genesis"}
    ).json()
    hit = body["hits"][0]
    # Equal relevance → ORDER BY rank, translation_id → KJV first → flat snippet == matches["KJV"].
    assert hit["snippet"] == hit["matches"]["KJV"]
    assert hit["snippet"] == hit["matches"][next(iter(hit["matches"]))]


def test_total_counts_verses_not_pairs(client: TestClient) -> None:
    body = client.get(
        "/v1/search", params={"q": "gen", "translations": "KJV,WEB,YLT", "book": "genesis"}
    ).json()
    assert body["total"] == 3  # not 9 (3 verses × 3 translations)


def test_translations_echo_and_primary(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": "gen", "translations": "YLT,KJV"}).json()
    assert body["translations"] == ["YLT", "KJV"]  # request order preserved
    assert body["translation"] == "YLT"  # primary = first resolved


def test_star_searches_all_loaded(client: TestClient) -> None:
    body = client.get(
        "/v1/search", params={"q": "gen", "translations": "*", "book": "genesis"}
    ).json()
    # sorted, all loaded — incl. the Greek SBLGNT and Hebrew OSHB, which have no English Genesis
    # verse so they carry no match for this hit (a translation lacking the verse is absent from
    # `matches`).
    assert body["translations"] == ["KJV", "OSHB", "SBLGNT", "WEB", "YLT"]
    assert set(body["hits"][0]["matches"].keys()) == {"KJV", "WEB", "YLT"}


def test_case_insensitive_ids(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": "gen", "translations": "kjv,ylt"}).json()
    assert body["translations"] == ["KJV", "YLT"]


def test_web_omission_asymmetry(client: TestClient) -> None:
    """WEB omits JHN 3:16 → that verse matches in KJV only; neighbours match in both."""
    body = client.get(
        "/v1/search", params={"q": "jhn", "translations": "KJV,WEB", "limit": 100}
    ).json()
    by_key = {(h["chapter"], h["verse"]): h for h in body["hits"]}
    assert set(by_key[(3, 16)]["matches"].keys()) == {"KJV"}
    assert set(by_key[(3, 15)]["matches"].keys()) == {"KJV", "WEB"}


def test_pagination_over_verses_non_overlapping(client: TestClient) -> None:
    page1 = client.get(
        "/v1/search", params={"q": "jhn", "translations": "KJV,WEB", "limit": 10, "offset": 0}
    ).json()
    page2 = client.get(
        "/v1/search", params={"q": "jhn", "translations": "KJV,WEB", "limit": 10, "offset": 10}
    ).json()
    refs1 = {h["reference"] for h in page1["hits"]}
    refs2 = {h["reference"] for h in page2["hits"]}
    assert page1["total"] == 30  # JHN 3:1-20 + 4:1-10 distinct verses
    assert len(refs1) == len(refs2) == 10
    assert not (refs1 & refs2)


def test_book_filter_multi(client: TestClient) -> None:
    body = client.get(
        "/v1/search", params={"q": "gen", "translations": "KJV,YLT", "book": "genesis"}
    ).json()
    assert body["book"] == "GEN"
    assert all(h["book"] == "GEN" for h in body["hits"])


# --- multi mode: errors + empty ------------------------------------------------------


def test_unknown_translation_is_404(client: TestClient) -> None:
    resp = client.get("/v1/search", params={"q": "gen", "translations": "KJV,NOPE"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "unknown_translation"


def test_malformed_query_is_400(client: TestClient) -> None:
    resp = client.get("/v1/search", params={"q": '"unbalanced', "translations": "KJV,YLT"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "invalid_search_query"
    assert "fts5_error" in body["error"]["detail"]


def test_zero_matches_is_200_empty(client: TestClient) -> None:
    resp = client.get("/v1/search", params={"q": "zebra", "translations": "KJV,YLT"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["hits"] == []
    assert body["translations"] == ["KJV", "YLT"]


def test_unknown_book_filter_is_400(client: TestClient) -> None:
    resp = client.get("/v1/search", params={"q": "gen", "translations": "KJV", "book": "hezekiah"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unknown_book"


# --- caching -------------------------------------------------------------------------


def test_cache_control_and_etag_304(client: TestClient) -> None:
    resp = client.get("/v1/search", params={"q": "gen", "translations": "KJV,YLT"})
    assert resp.headers["cache-control"] == CACHE_CONTROL
    etag = resp.headers["etag"]
    not_modified = client.get(
        "/v1/search",
        params={"q": "gen", "translations": "KJV,YLT"},
        headers={"If-None-Match": etag},
    )
    assert not_modified.status_code == 304
    assert not_modified.content == b""
