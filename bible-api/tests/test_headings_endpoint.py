"""The /v1/translations/{t}/headings/{book}/{chapter} endpoint against the synthetic corpus (fast).

Chapter read, response shape (anchor, before_verse, ordinal, reference), ordering, the
immutable-ETag 304, and the honesty split: a translation with NO headings → 200 empty (not 404);
unknown translation/book → 404; chapter < 1 → 422.

Synthetic corpus (apikit): WEB has two headings on JHN 3; KJV one on GEN 1; YLT has none.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

HEADING_KEYS = ["book", "chapter", "before_verse", "text", "ordinal", "reference"]


# --- chapter read --------------------------------------------------------------------


def test_chapter_read_echo_and_order(client: TestClient) -> None:
    body = client.get("/v1/translations/WEB/headings/JHN/3").json()
    assert (body["translation"], body["book"], body["chapter"]) == ("WEB", "JHN", 3)
    assert body["total"] == 2
    # Ordered by before_verse then ordinal.
    assert [(h["before_verse"], h["ordinal"], h["text"]) for h in body["headings"]] == [
        (1, 1, "Jesus Teaches Nicodemus"),
        (16, 2, "God's Love"),
    ]


def test_heading_shape_and_fields(client: TestClient) -> None:
    first = client.get("/v1/translations/WEB/headings/JHN/3").json()["headings"][0]
    assert list(first.keys()) == HEADING_KEYS
    assert first["book"] == "JHN"
    assert first["before_verse"] == 1
    assert first["text"] == "Jesus Teaches Nicodemus"
    assert first["reference"] == "John 3:1"


def test_other_translation_has_its_own_headings(client: TestClient) -> None:
    body = client.get("/v1/translations/KJV/headings/GEN/1").json()
    assert body["total"] == 1
    assert body["headings"][0]["text"] == "The Creation"


def test_translation_path_is_case_insensitive(client: TestClient) -> None:
    body = client.get("/v1/translations/web/headings/JHN/3").json()
    assert body["translation"] == "WEB"
    assert body["total"] == 2


# --- honest empty / absent (load-bearing) --------------------------------------------


def test_translation_without_headings_is_empty_200(client: TestClient) -> None:
    """YLT is loaded but ships no headings — like the real BSB. 200 empty, NOT 404."""
    resp = client.get("/v1/translations/YLT/headings/JHN/3")
    assert resp.status_code == 200
    body = resp.json()
    assert (body["translation"], body["total"], body["headings"]) == ("YLT", 0, [])


def test_chapter_without_headings_is_empty_200(client: TestClient) -> None:
    resp = client.get("/v1/translations/WEB/headings/JHN/4")  # valid chapter, no headings
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_out_of_range_chapter_is_empty_200(client: TestClient) -> None:
    resp = client.get("/v1/translations/WEB/headings/JHN/99")  # overlay → empty, not 404
    assert resp.status_code == 200
    assert resp.json()["headings"] == []


# --- errors --------------------------------------------------------------------------


def test_unknown_translation_is_404(client: TestClient) -> None:
    resp = client.get("/v1/translations/NOPE/headings/JHN/3")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "unknown_translation"


def test_unknown_book_is_404(client: TestClient) -> None:
    resp = client.get("/v1/translations/WEB/headings/Hezekiah/3")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "unknown_book"


def test_non_positive_chapter_is_422(client: TestClient) -> None:
    assert client.get("/v1/translations/WEB/headings/JHN/0").status_code == 422


# --- caching -------------------------------------------------------------------------


def test_cache_control_and_etag_304(client: TestClient) -> None:
    resp = client.get("/v1/translations/WEB/headings/JHN/3")
    assert resp.headers["cache-control"] == CACHE_CONTROL
    etag = resp.headers["etag"]
    not_modified = client.get(
        "/v1/translations/WEB/headings/JHN/3", headers={"If-None-Match": etag}
    )
    assert not_modified.status_code == 304
    assert not_modified.content == b""
