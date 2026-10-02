"""GET /v1/translations/{translation}/documents[/{slug}] — a translation's documents (ADR-0012).

The synthetic corpus (apikit) gives KJV four made-up documents: two book introductions (GEN's
places the PNG; EXO's the JPEG, then the PNG), front matter and an about document. YLT has none.
The list shows summaries in kind order, then ordinal; one document comes back with its Markdown
text and the images it places. Both carry the immutable caching of every read; an unknown
translation or slug is a 404 envelope, an unknown filter value a 400.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from typing import Any

import pytest
from apikit import CHART_JPEG, DIAGRAM_PNG, GEN_INTRODUCTION
from bible_api.errors import CACHE_CONTROL
from bible_core.documents import DOCUMENT_KINDS
from fastapi.testclient import TestClient

LIST = "/v1/translations/KJV/documents"
GEN = "/v1/translations/KJV/documents/introduction-gen"


def _slugs(body: dict[str, Any]) -> list[str]:
    return [d["slug"] for d in body["documents"]]


def test_the_list_shape_and_order(client: TestClient) -> None:
    body = client.get(LIST).json()
    assert list(body) == ["translation", "book", "kind", "total", "documents"]
    assert (body["translation"], body["book"], body["kind"], body["total"]) == (
        "KJV",
        None,
        None,
        4,
    )
    # front matter, then the introductions by ordinal, then about
    assert _slugs(body) == [
        "made-up-preface",
        "introduction-gen",
        "introduction-exo",
        "about-the-edition",
    ]
    assert body["documents"][1] == {
        "slug": "introduction-gen",
        "kind": "book-introduction",
        "title": "Made-up Genesis",
        "book": "GEN",
        "ordinal": 1,
    }
    assert body["documents"][0]["book"] is None


@pytest.mark.parametrize("book", ["GEN", "gen", "Genesis", "Gen"])
def test_book_filter_takes_any_alias(client: TestClient, book: str) -> None:
    body = client.get(LIST, params={"book": book}).json()
    assert (body["book"], body["total"], _slugs(body)) == ("GEN", 1, ["introduction-gen"])


def test_kind_filter(client: TestClient) -> None:
    body = client.get(LIST, params={"kind": "book-introduction"}).json()
    assert body["kind"] == "book-introduction"
    assert _slugs(body) == ["introduction-gen", "introduction-exo"]


def test_the_filters_combine(client: TestClient) -> None:
    both = client.get(LIST, params={"book": "EXO", "kind": "book-introduction"}).json()
    assert _slugs(both) == ["introduction-exo"]
    none = client.get(LIST, params={"book": "EXO", "kind": "about"}).json()
    assert (none["total"], none["documents"]) == (0, [])


@pytest.mark.parametrize(
    "params",
    [
        {"book": "REV"},  # a known book with no introduction
        {"kind": "reading-plan"},  # a known kind with no document
    ],
)
def test_a_filter_matching_nothing_is_200_empty(client: TestClient, params: dict[str, str]) -> None:
    response = client.get(LIST, params=params)
    assert response.status_code == 200
    assert (response.json()["total"], response.json()["documents"]) == (0, [])


def test_a_known_translation_with_no_documents_is_200_empty(client: TestClient) -> None:
    response = client.get("/v1/translations/YLT/documents")
    assert response.status_code == 200
    assert response.json() == {
        "translation": "YLT",
        "book": None,
        "kind": None,
        "total": 0,
        "documents": [],
    }


def test_an_unknown_kind_is_400(client: TestClient) -> None:
    response = client.get(LIST, params={"kind": "preface"})
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "unknown_kind",
            "message": "unknown document kind 'preface'",
            "detail": {"kind": "preface", "available": list(DOCUMENT_KINDS)},
        }
    }


def test_an_unknown_book_filter_is_400(client: TestClient) -> None:
    response = client.get(LIST, params={"book": "Hezekiah"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_book"


@pytest.mark.parametrize("path", [LIST, GEN])
def test_an_unknown_translation_is_404(client: TestClient, path: str) -> None:
    response = client.get(path.replace("KJV", "NOPE"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_translation"


def test_one_document_in_full(client: TestClient) -> None:
    body = client.get(GEN).json()
    assert body == {
        "translation": "KJV",
        "slug": "introduction-gen",
        "kind": "book-introduction",
        "title": "Made-up Genesis",
        "book": "GEN",
        "ordinal": 1,
        "text": GEN_INTRODUCTION,
        "images": [{"name": "diagram.png", "media_type": "image/png", "width": 5, "height": 4}],
    }


def test_images_come_in_order_of_first_use(client: TestClient) -> None:
    images = client.get("/v1/translations/KJV/documents/introduction-exo").json()["images"]
    assert images == [
        {"name": "chart-01.jpg", "media_type": "image/jpeg", "width": 20, "height": 10},
        {"name": "diagram.png", "media_type": "image/png", "width": 5, "height": 4},
    ]


def test_a_document_without_images_lists_none(client: TestClient) -> None:
    body = client.get("/v1/translations/KJV/documents/about-the-edition").json()
    assert (body["book"], body["images"]) == (None, [])


def test_each_image_is_served_by_the_assets_endpoint(client: TestClient) -> None:
    images = client.get("/v1/translations/KJV/documents/introduction-exo").json()["images"]
    served = [client.get(f"/v1/translations/KJV/assets/{i['name']}").content for i in images]
    assert served == [CHART_JPEG, DIAGRAM_PNG]


def test_the_translation_id_is_case_insensitive(client: TestClient) -> None:
    assert client.get("/v1/translations/kjv/documents/introduction-gen").json()["slug"] == (
        "introduction-gen"
    )


@pytest.mark.parametrize(
    ("translation", "slug"),
    [
        ("KJV", "introduction-rev"),  # no such slug
        ("KJV", "Introduction-GEN"),  # slugs match exactly
        ("YLT", "introduction-gen"),  # another translation's document
    ],
)
def test_a_slug_the_translation_lacks_is_404(
    client: TestClient, translation: str, slug: str
) -> None:
    response = client.get(f"/v1/translations/{translation}/documents/{slug}")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "unknown_document",
            "message": f"unknown document {slug!r} in translation {translation!r}",
            "detail": {"translation": translation, "slug": slug},
        }
    }


@pytest.mark.parametrize("path", [LIST, GEN])
def test_immutable_caching_and_304(client: TestClient, path: str) -> None:
    first = client.get(path)
    etag = first.headers["etag"]
    assert etag.startswith('"') and not etag.startswith("W/")
    assert first.headers["cache-control"] == CACHE_CONTROL
    assert first.headers["vary"] == "Origin"
    revalidated = client.get(path, headers={"If-None-Match": etag})
    assert revalidated.status_code == 304
    assert revalidated.content == b""


def test_the_contract_declares_both_bodies() -> None:
    from bible_api.app import create_app

    paths = create_app(enable_semantic=False).openapi()["paths"]
    for path, model in [
        ("/v1/translations/{translation}/documents", "DocumentsResponse"),
        ("/v1/translations/{translation}/documents/{slug}", "Document"),
    ]:
        schema = paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema == {"$ref": f"#/components/schemas/{model}"}
