"""/v1/verses/{ref}: every grammar form, both shapes, translations handling."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from typing import Any

from apikit import verse_text
from fastapi.testclient import TestClient


def _verse_numbers(body: dict[str, Any]) -> list[int]:
    return [v["verse"] for v in body["verses"]]


def test_single_verse_parallel(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:16", params={"translations": "KJV"}).json()
    assert body["reference"] == "John 3:16"
    assert body["translations"] == ["KJV"]
    assert body["verses"] == [
        {
            "book": "JHN",
            "chapter": 3,
            "verse": 16,
            "reference": "John 3:16",
            "text": {"KJV": verse_text("JHN", 3, 16, "KJV")},
        }
    ]


def test_verse_range(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:16-18", params={"translations": "KJV"}).json()
    assert _verse_numbers(body) == [16, 17, 18]


def test_verse_list(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:16,18,20", params={"translations": "KJV"}).json()
    assert _verse_numbers(body) == [16, 18, 20]


def test_whole_chapter(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3", params={"translations": "KJV"}).json()
    assert _verse_numbers(body) == list(range(1, 21))


def test_chapter_range(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3-4", params={"translations": "KJV"}).json()
    chapters = {v["chapter"] for v in body["verses"]}
    assert chapters == {3, 4}
    assert len(body["verses"]) == 30  # 20 + 10


def test_cross_chapter_range(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:18-4:2", params={"translations": "KJV"}).json()
    positions = [(v["chapter"], v["verse"]) for v in body["verses"]]
    assert positions == [(3, 18), (3, 19), (3, 20), (4, 1), (4, 2)]


def test_multi_translation(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:17", params={"translations": "KJV,WEB,YLT"}).json()
    assert body["translations"] == ["KJV", "WEB", "YLT"]
    text = body["verses"][0]["text"]
    assert text == {
        "KJV": verse_text("JHN", 3, 17, "KJV"),
        "WEB": verse_text("JHN", 3, 17, "WEB"),
        "YLT": verse_text("JHN", 3, 17, "YLT"),
    }


def test_default_translation_when_omitted(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:17").json()
    assert body["translations"] == ["KJV"]


def test_translation_ids_are_case_insensitive(client: TestClient) -> None:
    body = client.get("/v1/verses/John 3:17", params={"translations": "kjv,web"}).json()
    assert body["translations"] == ["KJV", "WEB"]


def test_grouped_shape(client: TestClient) -> None:
    body = client.get(
        "/v1/verses/John 3:16-17", params={"translations": "KJV,WEB", "format": "grouped"}
    ).json()
    assert body["reference"] == "John 3:16-17"
    assert [v["verse"] for v in body["translations"]["KJV"]] == [16, 17]
    assert [v["verse"] for v in body["translations"]["WEB"]] == [17]  # WEB omits 3:16
