"""/v1/books: the 66-book catalog (byte-precise) with the immutable-cache pattern."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient

CACHE_CONTROL = "public, max-age=31536000, immutable"


def test_count_and_canonical_order(client: TestClient) -> None:
    body = client.get("/v1/books").json()
    books = body["books"]
    assert len(books) == 66
    assert [b["canonical_order"] for b in books] == list(range(1, 67))


def test_key_order(client: TestClient) -> None:
    body = client.get("/v1/books").json()
    assert list(body.keys()) == ["books"]
    assert list(body["books"][0].keys()) == [
        "id",
        "name",
        "testament",
        "chapter_count",
        "canonical_order",
    ]


def test_first_and_last_book(client: TestClient) -> None:
    books = client.get("/v1/books").json()["books"]
    assert books[0] == {
        "id": "GEN",
        "name": "Genesis",
        "testament": "OT",
        "chapter_count": 1,  # corpus has Genesis 1 only
        "canonical_order": 1,
    }
    assert books[-1]["id"] == "REV"
    assert books[-1]["canonical_order"] == 66


def test_chapter_count_for_populated_and_empty_books(client: TestClient) -> None:
    by_id = {b["id"]: b for b in client.get("/v1/books").json()["books"]}
    assert by_id["JHN"]["chapter_count"] == 2  # chapters 3 and 4 in the corpus
    assert by_id["REV"]["chapter_count"] is None  # no verses loaded


def test_immutable_cache_and_304(client: TestClient) -> None:
    response = client.get("/v1/books")
    assert response.headers["cache-control"] == CACHE_CONTROL
    etag = response.headers["etag"]
    not_modified = client.get("/v1/books", headers={"If-None-Match": etag})
    assert not_modified.status_code == 304
    assert not_modified.content == b""
