"""The /v1/translations/{t}/notes/{book}/{chapter} endpoint against the synthetic corpus (fast).

Chapter read + ?verse narrowing, the response shape (anchor, char_offset, marker, ordinal,
nested cross-refs), ordering, the immutable-ETag 304, and the load-bearing honesty split:
a known translation with NO notes → 200 empty; an unknown translation → 404. WEB carries
committed public-domain footnotes (ADR-0004); YLT has none. No real NET data.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

NOTE_KEYS = [
    "book",
    "chapter",
    "verse",
    "reference",
    "type",
    "text",
    "char_offset",
    "marker",
    "ordinal",
    "cross_references",
]


# --- chapter read --------------------------------------------------------------------


def test_chapter_read_echo_and_order(client: TestClient) -> None:
    body = client.get("/v1/translations/KJV/notes/JHN/3").json()
    assert (body["translation"], body["book"], body["chapter"], body["verse"]) == (
        "KJV",
        "JHN",
        3,
        None,
    )
    assert body["total"] == 3
    # Ordered by verse then ordinal: JHN 3:16 #1, JHN 3:16 #2, JHN 3:17 #1.
    assert [(n["verse"], n["ordinal"], n["type"]) for n in body["notes"]] == [
        (16, 1, "tn"),
        (16, 2, "sn"),
        (17, 1, "tc"),
    ]


def test_note_shape_and_fields(client: TestClient) -> None:
    notes = client.get("/v1/translations/KJV/notes/JHN/3").json()["notes"]
    first = notes[0]
    assert list(first.keys()) == NOTE_KEYS
    assert first["book"] == "JHN"
    assert first["reference"] == "John 3:16"
    assert first["text"] == "On the Greek behind 'so loved'."
    assert first["char_offset"] == 8
    assert first["marker"] == "1"


def test_note_cross_references(client: TestClient) -> None:
    first = client.get("/v1/translations/KJV/notes/JHN/3").json()["notes"][0]
    xrefs = first["cross_references"]
    assert xrefs == [
        {
            "to_book": "GEN",
            "to_chapter": 1,
            "to_verse_start": 1,
            "to_verse_end": None,
            "reference": "Genesis 1:1",
        },
        {
            "to_book": "JHN",
            "to_chapter": 4,
            "to_verse_start": 2,
            "to_verse_end": 4,
            "reference": "John 4:2-4",
        },
    ]


def test_plain_note_has_null_type(client: TestClient) -> None:
    notes = client.get("/v1/translations/KJV/notes/GEN/1").json()["notes"]
    assert len(notes) == 1
    assert notes[0]["type"] is None
    assert notes[0]["cross_references"] == []


# --- ?verse narrowing ----------------------------------------------------------------


def test_verse_filter_narrows(client: TestClient) -> None:
    body = client.get("/v1/translations/KJV/notes/JHN/3", params={"verse": 16}).json()
    assert body["verse"] == 16
    assert body["total"] == 2
    assert {n["verse"] for n in body["notes"]} == {16}


def test_verse_filter_single(client: TestClient) -> None:
    body = client.get("/v1/translations/KJV/notes/JHN/3", params={"verse": 17}).json()
    assert [n["type"] for n in body["notes"]] == ["tc"]


def test_verse_filter_absent_is_empty_200(client: TestClient) -> None:
    resp = client.get("/v1/translations/KJV/notes/JHN/3", params={"verse": 99})
    assert resp.status_code == 200
    assert resp.json()["notes"] == []


def test_non_positive_verse_is_422(client: TestClient) -> None:
    assert client.get("/v1/translations/KJV/notes/JHN/3", params={"verse": 0}).status_code == 422


# --- the honest empty / absent behavior (load-bearing) -------------------------------


def test_known_translation_no_notes_is_empty_200(client: TestClient) -> None:
    """YLT is loaded but has zero notes — a translation with no notes. 200 empty, NOT 404."""
    resp = client.get("/v1/translations/YLT/notes/JHN/3")
    assert resp.status_code == 200
    body = resp.json()
    assert (body["translation"], body["total"], body["notes"]) == ("YLT", 0, [])


def test_web_chapter_serves_public_domain_notes(client: TestClient) -> None:
    """ADR-0004: WEB's own public-domain footnotes ship and read back, not an empty list."""
    body = client.get("/v1/translations/WEB/notes/GEN/1").json()
    assert (body["translation"], body["book"], body["chapter"]) == ("WEB", "GEN", 1)
    assert body["total"] == 2
    first = body["notes"][0]
    # Verse-level anchor for v1: char_offset 0, type null, no caller marker, no cross-refs.
    assert (first["verse"], first["type"], first["char_offset"], first["marker"]) == (
        1,
        None,
        0,
        None,
    )
    assert first["reference"] == "Genesis 1:1"
    assert first["cross_references"] == []


def test_empty_chapter_is_empty_200(client: TestClient) -> None:
    resp = client.get("/v1/translations/KJV/notes/JHN/4")  # valid chapter, no notes
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_unknown_translation_is_404(client: TestClient) -> None:
    resp = client.get("/v1/translations/NOPE/notes/JHN/3")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "unknown_translation"


def test_unknown_book_is_404(client: TestClient) -> None:
    resp = client.get("/v1/translations/KJV/notes/Hezekiah/3")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "unknown_book"


def test_translation_path_is_case_insensitive(client: TestClient) -> None:
    body = client.get("/v1/translations/kjv/notes/JHN/3").json()
    assert body["translation"] == "KJV"
    assert body["total"] == 3


# --- caching -------------------------------------------------------------------------


def test_cache_control_and_etag_304(client: TestClient) -> None:
    resp = client.get("/v1/translations/KJV/notes/JHN/3")
    assert resp.headers["cache-control"] == CACHE_CONTROL
    etag = resp.headers["etag"]
    not_modified = client.get("/v1/translations/KJV/notes/JHN/3", headers={"If-None-Match": etag})
    assert not_modified.status_code == 304
    assert not_modified.content == b""
