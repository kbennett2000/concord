"""/v1/cross-references/{ref}: paths, ordering, pagination, include_text, empty results.

Corpus cross-refs (from apikit): John 3:16 → GEN 1:1 (50), 1JN 1:1 (40), JHN 4:2-4 (30),
JHN 4:1 (5); John 4:1 → JHN 3:16 (which WEB omits).
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from apikit import verse_text
from fastapi.testclient import TestClient


def test_single_verse(client: TestClient) -> None:
    body = client.get("/v1/cross-references/John 3:16").json()
    assert body["reference"] == "John 3:16"
    assert body["translation"] is None  # include_text not requested
    assert body["total"] == 4
    assert [e["votes"] for e in body["cross_references"]] == [50, 40, 30, 5]  # votes desc
    first = body["cross_references"][0]
    assert first["from"] == {"book": "JHN", "chapter": 3, "verse": 16, "reference": "John 3:16"}
    assert first["to"]["reference"] == "Genesis 1:1"
    assert first["text"] is None


def test_range_target_reference(client: TestClient) -> None:
    body = client.get("/v1/cross-references/John 3:16").json()
    target = next(e["to"] for e in body["cross_references"] if e["to"]["book"] == "JHN")
    assert target["verse_start"] == 2
    assert target["verse_end"] == 4
    assert target["reference"] == "John 4:2-4"


def test_min_votes_filter(client: TestClient) -> None:
    body = client.get("/v1/cross-references/John 3:16", params={"min_votes": 10}).json()
    assert body["total"] == 3  # excludes the votes-5 entry
    assert all(e["votes"] >= 10 for e in body["cross_references"])


def test_pagination_non_overlapping(client: TestClient) -> None:
    page1 = client.get("/v1/cross-references/John 3:16", params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/v1/cross-references/John 3:16", params={"limit": 2, "offset": 2}).json()
    refs1 = {e["to"]["reference"] for e in page1["cross_references"]}
    refs2 = {e["to"]["reference"] for e in page2["cross_references"]}
    assert len(refs1) == 2
    assert len(refs2) == 2
    assert not (refs1 & refs2)


def test_range_input_spans_sources(client: TestClient) -> None:
    body = client.get("/v1/cross-references/John 3:16-4:1").json()
    assert body["total"] == 5  # 4 from 3:16 + 1 from 4:1
    sources = {(e["from"]["chapter"], e["from"]["verse"]) for e in body["cross_references"]}
    assert sources == {(3, 16), (4, 1)}


def test_include_text_hydrates_target(client: TestClient) -> None:
    body = client.get(
        "/v1/cross-references/John 3:16", params={"include_text": "true", "translation": "KJV"}
    ).json()
    assert body["translation"] == "KJV"
    by_ref = {e["to"]["reference"]: e["text"] for e in body["cross_references"]}
    assert by_ref["Genesis 1:1"] == verse_text("GEN", 1, 1, "KJV")
    assert by_ref["John 4:2-4"] == verse_text("JHN", 4, 2, "KJV")  # start verse of the range


def test_include_text_null_when_target_missing_in_translation(client: TestClient) -> None:
    # John 4:1 → JHN 3:16, which WEB omits.
    body = client.get(
        "/v1/cross-references/John 4:1", params={"include_text": "true", "translation": "WEB"}
    ).json()
    entry = body["cross_references"][0]
    assert entry["to"]["reference"] == "John 3:16"
    assert entry["text"] is None


def test_verse_with_no_cross_refs_is_200_empty(client: TestClient) -> None:
    response = client.get("/v1/cross-references/Genesis 1:2")  # exists, no cross-refs
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["cross_references"] == []
