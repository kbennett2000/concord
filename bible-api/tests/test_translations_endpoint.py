"""/v1/translations: loaded-translation catalog (byte-precise) with immutable cache."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient

CACHE_CONTROL = "public, max-age=31536000, immutable"


def test_shape_and_order(client: TestClient) -> None:
    body = client.get("/v1/translations").json()
    assert list(body.keys()) == ["translations"]
    translations = body["translations"]
    # ordered by id; SBLGNT (Greek NT) + OSHB (Hebrew OT) are the word-study original-language texts
    assert [t["id"] for t in translations] == ["KJV", "OSHB", "SBLGNT", "WEB", "YLT"]
    assert {t["id"]: t["direction"] for t in translations}["OSHB"] == "rtl"
    assert list(translations[0].keys()) == [
        "id",
        "name",
        "language",
        "direction",
        "versification",
        "attribution",
    ]
    assert all(t["direction"] in ("ltr", "rtl") for t in translations)


def test_metadata(client: TestClient) -> None:
    by_id = {t["id"]: t for t in client.get("/v1/translations").json()["translations"]}
    kjv = by_id["KJV"]
    assert kjv["name"] == "King James Version"
    assert kjv["language"] == "en"
    assert kjv["versification"] == "standard"
    assert kjv["attribution"]  # present and non-empty


def test_immutable_cache(client: TestClient) -> None:
    response = client.get("/v1/translations")
    assert response.headers["cache-control"] == CACHE_CONTROL
    assert "etag" in response.headers
