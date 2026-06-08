"""The /v1/strongs + /v1/strongs/{id} endpoints against the synthetic corpus (fast).

Browse + q/language filters + pagination/echo, numeric ordering, detail (full shape incl.
definition), id normalization (lower-case + leading zeros), 404 unknown_strongs, and the
immutable-ETag 304.

Synthetic lexicon (apikit): G25 ἀγαπάω, G26 ἀγάπη (grc), H430 אֱלֹהִים (hbo). No dependence on
the real TBESG dataset.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

SUMMARY_KEYS = ["strongs_id", "language", "lemma", "transliteration", "gloss"]


# --- browse + filters ----------------------------------------------------------------


def test_browse_default_order_and_echo(client: TestClient) -> None:
    body = client.get("/v1/strongs").json()
    assert (body["q"], body["language"]) == (None, None)
    assert (body["limit"], body["offset"], body["total"]) == (50, 0, 3)
    # Numeric order within language: G25, G26 (grc) then H430 (hbo).
    assert [e["strongs_id"] for e in body["entries"]] == ["G25", "G26", "H430"]
    assert list(body["entries"][0].keys()) == SUMMARY_KEYS


def test_filter_q_over_gloss(client: TestClient) -> None:
    body = client.get("/v1/strongs", params={"q": "love"}).json()
    assert [e["strongs_id"] for e in body["entries"]] == ["G25", "G26"]
    assert body["q"] == "love"


def test_filter_q_over_transliteration(client: TestClient) -> None:
    body = client.get("/v1/strongs", params={"q": "elōhîm"}).json()
    assert [e["strongs_id"] for e in body["entries"]] == ["H430"]


def test_filter_language(client: TestClient) -> None:
    body = client.get("/v1/strongs", params={"language": "hbo"}).json()
    assert [e["strongs_id"] for e in body["entries"]] == ["H430"]
    assert body["language"] == "hbo"


def test_pagination_non_overlapping(client: TestClient) -> None:
    p1 = client.get("/v1/strongs", params={"limit": 2, "offset": 0}).json()
    p2 = client.get("/v1/strongs", params={"limit": 2, "offset": 2}).json()
    assert p1["total"] == 3
    assert {e["strongs_id"] for e in p1["entries"]}.isdisjoint(
        {e["strongs_id"] for e in p2["entries"]}
    )


# --- detail --------------------------------------------------------------------------


def test_detail_full_shape(client: TestClient) -> None:
    body = client.get("/v1/strongs/G26").json()
    assert body == {
        "strongs_id": "G26",
        "language": "grc",
        "lemma": "ἀγάπη",
        "transliteration": "agapē",
        "gloss": "love",
        "definition": "love, goodwill, esteem.",
        "source": "STEP Bible",
    }


def test_detail_id_normalized(client: TestClient) -> None:
    # lower-case letter and zero-padding both resolve to the collapsed-base id G26.
    assert client.get("/v1/strongs/g0026").json()["strongs_id"] == "G26"
    assert client.get("/v1/strongs/g26").json()["strongs_id"] == "G26"


def test_detail_unknown_404(client: TestClient) -> None:
    resp = client.get("/v1/strongs/G99999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "unknown_strongs"
    assert body["error"]["detail"]["strongs_id"] == "G99999"


# --- caching -------------------------------------------------------------------------


def test_immutable_etag_304_all_endpoints(client: TestClient) -> None:
    for url in ("/v1/strongs", "/v1/strongs/G26"):
        resp = client.get(url)
        assert resp.headers["cache-control"] == CACHE_CONTROL
        etag = resp.headers["etag"]
        not_modified = client.get(url, headers={"If-None-Match": etag})
        assert not_modified.status_code == 304
        assert not_modified.content == b""
