"""/v1/notes/search against the synthetic corpus (fast): word/phrase matching, snippet marking,
the translation/type/book filters, ordering + pagination, the honest-empty and unknown-filter
splits, case-insensitive translation, and the immutable-ETag 304.

Synthetic notes only (apikit): KJV has notes, WEB carries committed public-domain footnotes
(ADR-0004), YLT has none. The token "note" appears in 4 KJV notes (JHN 3:16 sn, JHN 3:17 tc,
GEN 2:1, 1JN 1:1) — WEB's notes use distinct vocabulary so those totals are unchanged;
"tiebreak fixture note" is identical in GEN 2:1 and 1JN 1:1 so the canonical tiebreak is
observable. No real NET data.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

HIT_KEYS = [
    "book",
    "chapter",
    "verse",
    "reference",
    "translation",
    "type",
    "char_offset",
    "marker",
    "ordinal",
    "snippet",
]


# --- matching ------------------------------------------------------------------------


def test_single_word(client: TestClient) -> None:
    body = client.get("/v1/notes/search", params={"q": "note"}).json()
    assert body["translation"] is None
    assert body["type"] is None
    assert body["book"] is None
    assert body["total"] == 4  # JHN 3:16, JHN 3:17, GEN 2:1, 1JN 1:1
    assert {hit["book"] for hit in body["hits"]} == {"JHN", "GEN", "1JN"}


def test_phrase_match(client: TestClient) -> None:
    body = client.get("/v1/notes/search", params={"q": '"divine love"'}).json()
    assert body["total"] == 1
    assert body["hits"][0]["reference"] == "John 3:16"


def test_snippet_has_markers(client: TestClient) -> None:
    body = client.get("/v1/notes/search", params={"q": "study"}).json()
    assert "<mark>study</mark>" in body["hits"][0]["snippet"]


def test_hit_shape_omits_cross_references(client: TestClient) -> None:
    hit = client.get("/v1/notes/search", params={"q": "study"}).json()["hits"][0]
    assert list(hit.keys()) == HIT_KEYS
    assert "cross_references" not in hit
    assert (hit["book"], hit["reference"], hit["translation"], hit["type"]) == (
        "JHN",
        "John 3:16",
        "KJV",
        "sn",
    )
    assert (hit["char_offset"], hit["marker"], hit["ordinal"]) == (20, "2", 2)


# --- filters -------------------------------------------------------------------------


def test_translation_filter(client: TestClient) -> None:
    body = client.get("/v1/notes/search", params={"q": "note", "translation": "KJV"}).json()
    assert body["translation"] == "KJV"
    assert body["total"] == 4
    assert all(hit["translation"] == "KJV" for hit in body["hits"])


def test_translation_filter_case_insensitive(client: TestClient) -> None:
    body = client.get("/v1/notes/search", params={"q": "note", "translation": "kjv"}).json()
    assert body["translation"] == "KJV"
    assert body["total"] == 4


def test_type_filter(client: TestClient) -> None:
    body = client.get("/v1/notes/search", params={"q": "note", "type": "tc"}).json()
    assert body["type"] == "tc"
    assert body["total"] == 1
    assert body["hits"][0]["type"] == "tc"
    assert body["hits"][0]["reference"] == "John 3:17"


def test_book_filter(client: TestClient) -> None:
    body = client.get("/v1/notes/search", params={"q": "note", "book": "john"}).json()
    assert body["book"] == "JHN"
    assert body["total"] == 2
    assert all(hit["book"] == "JHN" for hit in body["hits"])


# --- ordering + pagination -----------------------------------------------------------


def test_canonical_tiebreak_across_books(client: TestClient) -> None:
    # "A tiebreak fixture note." is identical in GEN 2:1 and 1JN 1:1 → tie on rank, canonical wins.
    body = client.get("/v1/notes/search", params={"q": "tiebreak"}).json()
    assert [hit["book"] for hit in body["hits"]] == ["GEN", "1JN"]


def test_pagination_non_overlapping(client: TestClient) -> None:
    page1 = client.get("/v1/notes/search", params={"q": "note", "limit": 2, "offset": 0}).json()
    page2 = client.get("/v1/notes/search", params={"q": "note", "limit": 2, "offset": 2}).json()
    keys1 = {(h["book"], h["chapter"], h["verse"], h["ordinal"]) for h in page1["hits"]}
    keys2 = {(h["book"], h["chapter"], h["verse"], h["ordinal"]) for h in page2["hits"]}
    assert page1["total"] == 4
    assert len(keys1) == 2
    assert len(keys2) == 2
    assert not (keys1 & keys2)


# --- honest empty --------------------------------------------------------------------


def test_zero_matches_is_200_empty(client: TestClient) -> None:
    response = client.get("/v1/notes/search", params={"q": "zebra"})
    assert response.status_code == 200
    body = response.json()
    assert body["hits"] == []
    assert body["total"] == 0


def test_known_translation_no_notes_is_200_empty(client: TestClient) -> None:
    """YLT is loaded but ships zero notes. 200 empty, never 404."""
    response = client.get("/v1/notes/search", params={"q": "note", "translation": "YLT"})
    assert response.status_code == 200
    body = response.json()
    assert (body["translation"], body["total"], body["hits"]) == ("YLT", 0, [])


def test_web_public_domain_note_is_searchable(client: TestClient) -> None:
    """ADR-0004: WEB's public-domain footnotes are FTS-searchable on a stock build."""
    body = client.get("/v1/notes/search", params={"q": "Elohim", "translation": "WEB"}).json()
    assert body["translation"] == "WEB"
    assert body["total"] == 1
    hit = body["hits"][0]
    assert (hit["book"], hit["reference"], hit["translation"]) == ("GEN", "Genesis 1:1", "WEB")


# --- error paths ---------------------------------------------------------------------


def test_missing_q_is_422(client: TestClient) -> None:
    assert client.get("/v1/notes/search").status_code == 422


def test_empty_q_is_422(client: TestClient) -> None:
    assert client.get("/v1/notes/search", params={"q": ""}).status_code == 422


def test_q_too_long_is_422(client: TestClient) -> None:
    response = client.get("/v1/notes/search", params={"q": "a" * 1001})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_parameter"


def test_limit_out_of_range_is_422(client: TestClient) -> None:
    assert client.get("/v1/notes/search", params={"q": "note", "limit": 101}).status_code == 422
    assert client.get("/v1/notes/search", params={"q": "note", "limit": 0}).status_code == 422
    assert client.get("/v1/notes/search", params={"q": "note", "offset": -1}).status_code == 422


def test_malformed_query_is_400(client: TestClient) -> None:
    response = client.get("/v1/notes/search", params={"q": '"unbalanced'})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_search_query"
    assert "fts5_error" in body["error"]["detail"]


def test_unknown_translation_is_404(client: TestClient) -> None:
    response = client.get("/v1/notes/search", params={"q": "note", "translation": "XYZ"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_translation"


def test_unknown_type_is_400(client: TestClient) -> None:
    response = client.get("/v1/notes/search", params={"q": "note", "type": "bogus"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "unknown_type"
    assert body["error"]["detail"]["type"] == "bogus"
    assert "tn" in body["error"]["detail"]["available"]


def test_unknown_book_filter_is_400(client: TestClient) -> None:
    response = client.get("/v1/notes/search", params={"q": "note", "book": "hezekiah"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_book"


# --- caching -------------------------------------------------------------------------


def test_cache_control_and_etag_304(client: TestClient) -> None:
    resp = client.get("/v1/notes/search", params={"q": "note"})
    assert resp.headers["cache-control"] == CACHE_CONTROL
    etag = resp.headers["etag"]
    not_modified = client.get(
        "/v1/notes/search", params={"q": "note"}, headers={"If-None-Match": etag}
    )
    assert not_modified.status_code == 304
    assert not_modified.content == b""
