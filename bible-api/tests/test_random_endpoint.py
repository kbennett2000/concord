"""/v1/random: filters, contradiction, non-determinism, and the no-store cache break."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_returns_a_verse(client: TestClient) -> None:
    body = client.get("/v1/random", params={"translation": "KJV"}).json()
    assert body["translation"] == "KJV"
    assert body["book"] is None
    assert body["testament"] is None
    assert list(body["verse"].keys()) == ["book", "chapter", "verse", "reference", "text"]


def test_no_store_and_no_etag(client: TestClient) -> None:
    response = client.get("/v1/random", params={"translation": "KJV"})
    assert response.headers["cache-control"] == "no-store"
    assert "etag" not in response.headers  # the deliberate break from the cache pattern


def test_default_translation(client: TestClient) -> None:
    assert client.get("/v1/random").json()["translation"] == "KJV"


def test_book_filter_usfm_and_alias(client: TestClient) -> None:
    assert client.get("/v1/random", params={"book": "JHN"}).json()["verse"]["book"] == "JHN"
    body = client.get("/v1/random", params={"book": "john"}).json()
    assert body["book"] == "JHN"
    assert body["verse"]["book"] == "JHN"


def test_testament_filter_case_insensitive(client: TestClient) -> None:
    body = client.get("/v1/random", params={"testament": "ot"}).json()
    assert body["testament"] == "OT"
    assert body["verse"]["book"] == "GEN"  # the only OT book with verses in the corpus


def test_book_and_testament_compatible(client: TestClient) -> None:
    body = client.get("/v1/random", params={"book": "GEN", "testament": "OT"}).json()
    assert body["verse"]["book"] == "GEN"


def test_contradicting_filters_404_no_match(client: TestClient) -> None:
    response = client.get("/v1/random", params={"book": "GEN", "testament": "NT"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_match"


def test_non_deterministic(client: TestClient) -> None:
    seen = {
        tuple(client.get("/v1/random", params={"translation": "KJV"}).json()["verse"].values())
        for _ in range(20)
    }
    assert len(seen) >= 2  # negligible false-positive chance over 36 corpus verses


def test_unknown_translation_404(client: TestClient) -> None:
    assert client.get("/v1/random", params={"translation": "XYZ"}).status_code == 404


def test_unknown_book_filter_400(client: TestClient) -> None:
    response = client.get("/v1/random", params={"book": "hezekiah"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_book"


def test_bad_testament_422(client: TestClient) -> None:
    assert client.get("/v1/random", params={"testament": "XX"}).status_code == 422


def test_envelope_matches_verses_endpoint(client: TestClient) -> None:
    random_error = client.get("/v1/random", params={"book": "GEN", "testament": "NT"}).json()
    verses_error = client.get("/v1/verses/foo bar").json()
    assert set(random_error.keys()) == set(verses_error.keys()) == {"error"}
    assert set(random_error["error"].keys()) == set(verses_error["error"].keys())
