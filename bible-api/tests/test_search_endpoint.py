"""/v1/search happy paths, empty results, and pagination.

Reuses the Slice 4 corpus (deterministic verse text like ``"GEN 1:1 (KJV)"``, which FTS5
tokenizes case-insensitively): JHN 3:1-20 + 4:1-10, GEN 1:1-3, 1JN 1:1-3 across KJV/WEB/YLT.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_single_word(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": "gen", "translation": "KJV"}).json()
    assert body["translation"] == "KJV"
    assert body["book"] is None
    assert body["total"] == 3
    assert all(hit["book"] == "GEN" for hit in body["hits"])


def test_snippet_has_markers(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": "gen", "translation": "KJV"}).json()
    assert "<mark>" in body["hits"][0]["snippet"]


def test_reference_field(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": "gen", "translation": "KJV"}).json()
    assert {hit["reference"] for hit in body["hits"]} == {
        "Genesis 1:1",
        "Genesis 1:2",
        "Genesis 1:3",
    }


def test_multi_word_and(client: TestClient) -> None:
    # "gen kjv" → verses containing both → only the GEN/KJV verses
    body = client.get("/v1/search", params={"q": "gen kjv", "translation": "KJV"}).json()
    assert body["total"] == 3


def test_phrase(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": '"gen 1"', "translation": "KJV"}).json()
    assert body["total"] == 3  # GEN 1:1, 1:2, 1:3


def test_prefix(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": "ge*", "translation": "KJV"}).json()
    assert body["total"] == 3  # ge* → gen


def test_book_filter(client: TestClient) -> None:
    body = client.get(
        "/v1/search", params={"q": "kjv", "translation": "KJV", "book": "genesis"}
    ).json()
    assert body["book"] == "GEN"
    assert body["total"] == 3
    assert all(hit["book"] == "GEN" for hit in body["hits"])


def test_default_translation(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": "gen"}).json()
    assert body["translation"] == "KJV"


def test_pagination_non_overlapping(client: TestClient) -> None:
    page1 = client.get(
        "/v1/search", params={"q": "jhn", "translation": "KJV", "limit": 10, "offset": 0}
    ).json()
    page2 = client.get(
        "/v1/search", params={"q": "jhn", "translation": "KJV", "limit": 10, "offset": 10}
    ).json()
    refs1 = {hit["reference"] for hit in page1["hits"]}
    refs2 = {hit["reference"] for hit in page2["hits"]}
    assert page1["total"] == 30  # JHN 3:1-20 + 4:1-10
    assert len(refs1) == 10
    assert len(refs2) == 10
    assert not (refs1 & refs2)


def test_zero_matches_is_200_empty(client: TestClient) -> None:
    response = client.get("/v1/search", params={"q": "zebra", "translation": "KJV"})
    assert response.status_code == 200
    body = response.json()
    assert body["hits"] == []
    assert body["total"] == 0


def test_offset_beyond_total(client: TestClient) -> None:
    body = client.get("/v1/search", params={"q": "gen", "translation": "KJV", "offset": 100}).json()
    assert body["hits"] == []
    assert body["total"] == 3


def test_book_filter_with_zero_matches(client: TestClient) -> None:
    body = client.get(
        "/v1/search", params={"q": "jhn", "translation": "KJV", "book": "genesis"}
    ).json()
    assert body["hits"] == []
    assert body["total"] == 0
