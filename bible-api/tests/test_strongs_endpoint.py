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


# --- /v1/strongs/{id}/verses (the concordance) ---------------------------------------


def test_strongs_verses_order_and_echo(client: TestClient) -> None:
    body = client.get("/v1/strongs/G26/verses").json()
    # G26 is tagged in JHN 4:7 and 4:8 (canonical order); echoes defaults.
    assert (body["strongs_id"], body["text_id"]) == ("G26", "SBLGNT")
    assert (body["translation"], body["include_text"], body["total"]) == ("KJV", True, 2)
    assert [(v["book"], v["chapter"], v["verse"]) for v in body["verses"]] == [
        ("JHN", 4, 7),
        ("JHN", 4, 8),
    ]
    assert body["verses"][0]["reference"] == "John 4:7"
    # Default hydration is the API default translation (KJV), which has those verses.
    assert all(isinstance(v["text"], str) and v["text"] for v in body["verses"])


def test_strongs_verses_id_normalized(client: TestClient) -> None:
    assert client.get("/v1/strongs/g0026/verses").json()["strongs_id"] == "G26"


def test_strongs_verses_include_text_false(client: TestClient) -> None:
    body = client.get("/v1/strongs/G26/verses", params={"include_text": "false"}).json()
    assert body["translation"] is None
    assert all(v["text"] is None for v in body["verses"])


def test_strongs_verses_missing_text_is_null(client: TestClient) -> None:
    # G25 is tagged in JHN 3:16, which WEB omits → text null when hydrating with WEB (not an error).
    body = client.get("/v1/strongs/G25/verses", params={"translation": "WEB"}).json()
    assert body["total"] == 1
    assert body["verses"][0]["text"] is None


def test_strongs_verses_pagination(client: TestClient) -> None:
    p1 = client.get("/v1/strongs/G26/verses", params={"limit": 1, "offset": 0}).json()
    p2 = client.get("/v1/strongs/G26/verses", params={"limit": 1, "offset": 1}).json()
    assert p1["total"] == p2["total"] == 2
    assert p1["verses"][0]["verse"] != p2["verses"][0]["verse"]


def test_strongs_verses_unknown_404(client: TestClient) -> None:
    resp = client.get("/v1/strongs/G99999/verses")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "unknown_strongs"


def test_strongs_verses_bad_text_404(client: TestClient) -> None:
    assert client.get("/v1/strongs/G26/verses", params={"text": "NOPE"}).status_code == 404


def test_strongs_verses_hebrew_default_text(client: TestClient) -> None:
    # A Hebrew id (H…) defaults to the Hebrew text (OSHB); H430 occurs in GEN 1:1 + 1:2.
    body = client.get("/v1/strongs/H430/verses").json()
    assert body["text_id"] == "OSHB"
    assert [(v["book"], v["chapter"], v["verse"]) for v in body["verses"]] == [
        ("GEN", 1, 1),
        ("GEN", 1, 2),
    ]
    # Forcing the Greek text finds nothing (H430 is not in the Greek NT).
    assert client.get("/v1/strongs/H430/verses", params={"text": "SBLGNT"}).json()["total"] == 0


# --- /v1/verses/{ref}/words (the tagged tokens) --------------------------------------


def test_verse_words_order_and_lexicon_join(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:16/words").json()
    assert (body["reference"], body["text_id"], body["total"]) == ("John 3:16", "SBLGNT", 3)
    toks = body["tokens"]
    assert [t["position"] for t in toks] == [1, 2, 3]
    # pos2 G25 joins the lexicon (ἀγαπάω / "to love"); pos1 G9999 has no entry → null lemma.
    assert toks[1]["strongs_id"] == "G25"
    assert (toks[1]["lemma"], toks[1]["gloss"]) == ("ἀγαπάω", "to love")
    assert (toks[0]["strongs_id"], toks[0]["lemma"]) == ("G9999", None)
    # pos3 is untagged: null strongs + morph.
    assert (toks[2]["strongs_id"], toks[2]["morph_code"]) == (None, None)


def test_verse_words_empty_when_no_tokens(client: TestClient) -> None:
    # John 4:1 (NT → defaults to SBLGNT) has no seeded tokens → 200 empty (not an error).
    body = client.get("/v1/verses/John 4:1/words").json()
    assert (body["total"], body["tokens"]) == (0, [])


def test_verse_words_default_text_by_testament(client: TestClient) -> None:
    # An OT reference defaults to the Hebrew text (OSHB) with no explicit ?text=.
    body = client.get("/v1/verses/Genesis 1:1/words").json()
    assert body["text_id"] == "OSHB"
    elohim = next(t for t in body["tokens"] if t["strongs_id"] == "H430")
    assert elohim["gloss"] == "God"
    # An NT reference defaults to the Greek text (SBLGNT).
    assert client.get("/v1/verses/John 3:16/words").json()["text_id"] == "SBLGNT"


def test_verse_words_bad_reference_400(client: TestClient) -> None:
    assert client.get("/v1/verses/NotABook 99:99/words").status_code in (400, 404)


def test_verse_words_unparseable_400(client: TestClient) -> None:
    assert client.get("/v1/verses/@@@/words").status_code == 400


def test_verse_words_bad_text_404(client: TestClient) -> None:
    assert client.get("/v1/verses/John 3:16/words", params={"text": "NOPE"}).status_code == 404


# --- caching -------------------------------------------------------------------------


def test_immutable_etag_304_all_endpoints(client: TestClient) -> None:
    for url in (
        "/v1/strongs",
        "/v1/strongs/G26",
        "/v1/strongs/G26/verses",
        "/v1/verses/John 3:16/words",
    ):
        resp = client.get(url)
        assert resp.headers["cache-control"] == CACHE_CONTROL
        etag = resp.headers["etag"]
        not_modified = client.get(url, headers={"If-None-Match": etag})
        assert not_modified.status_code == 304
        assert not_modified.content == b""
