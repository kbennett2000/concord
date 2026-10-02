"""GET /v1/translations/{translation}/assets/{name} — a translation's images (ADR-0012).

The synthetic corpus (apikit) gives KJV a made-up JPEG a chart note names and a made-up PNG; YLT
has none. Bytes come back exactly as stored, with their media type and the immutable caching every
verse response carries; a translation or name that isn't there is a 404 envelope.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import pytest
from apikit import CHART_JPEG, DIAGRAM_PNG
from bible_api.errors import CACHE_CONTROL
from fastapi.testclient import TestClient

CHART = "/v1/translations/KJV/assets/chart-01.jpg"


@pytest.mark.parametrize(
    ("name", "media_type", "data"),
    [("chart-01.jpg", "image/jpeg", CHART_JPEG), ("diagram.png", "image/png", DIAGRAM_PNG)],
)
def test_the_bytes_come_back_exactly_with_their_media_type(
    client: TestClient, name: str, media_type: str, data: bytes
) -> None:
    response = client.get(f"/v1/translations/KJV/assets/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == media_type
    assert response.content == data
    assert response.headers["content-length"] == str(len(data))


def test_immutable_caching_with_a_stable_strong_etag(client: TestClient) -> None:
    first, second = client.get(CHART), client.get(CHART)
    etag = first.headers["etag"]
    assert etag.startswith('"') and not etag.startswith("W/")
    assert second.headers["etag"] == etag
    assert first.headers["cache-control"] == CACHE_CONTROL
    assert first.headers["vary"] == "Origin"
    assert first.headers["x-content-type-options"] == "nosniff"


def test_etags_differ_between_images(client: TestClient) -> None:
    other = client.get("/v1/translations/KJV/assets/diagram.png")
    assert client.get(CHART).headers["etag"] != other.headers["etag"]


def test_if_none_match_returns_304_with_no_body(client: TestClient) -> None:
    etag = client.get(CHART).headers["etag"]
    response = client.get(CHART, headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == etag
    assert response.headers["cache-control"] == CACHE_CONTROL


def test_the_translation_id_is_case_insensitive(client: TestClient) -> None:
    assert client.get("/v1/translations/kjv/assets/chart-01.jpg").content == CHART_JPEG


def test_an_unknown_translation_is_404(client: TestClient) -> None:
    response = client.get("/v1/translations/NOPE/assets/chart-01.jpg")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_translation"


@pytest.mark.parametrize(
    ("translation", "name"),
    [
        ("KJV", "chart-99.jpg"),  # no such name
        ("KJV", "CHART-01.JPG"),  # names match exactly
        ("KJV", "chart-01"),  # any shape: still absent, not a 422
        ("YLT", "chart-01.jpg"),  # another translation's image
    ],
)
def test_a_name_the_translation_lacks_is_404(
    client: TestClient, translation: str, name: str
) -> None:
    response = client.get(f"/v1/translations/{translation}/assets/{name}")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "unknown_asset",
            "message": f"unknown asset {name!r} in translation {translation!r}",
            "detail": {"translation": translation, "name": name},
        }
    }


def test_a_chart_note_names_an_image_the_endpoint_serves(client: TestClient) -> None:
    (chart,) = client.get("/v1/translations/KJV/notes/GEN/13").json()["notes"]
    assert (chart["type"], chart["label"], chart["image"]) == ("chart", "Chart", "chart-01.jpg")
    served = client.get(f"/v1/translations/KJV/assets/{chart['image']}")
    assert served.content == CHART_JPEG


def test_the_contract_declares_both_image_types() -> None:
    from bible_api.app import create_app

    operation = create_app(enable_semantic=False).openapi()["paths"][
        "/v1/translations/{translation}/assets/{name}"
    ]["get"]
    assert set(operation["responses"]["200"]["content"]) == {"image/jpeg", "image/png"}
