"""Every response carries X-Content-Type-Options: nosniff (Slice HS-4)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from fastapi.testclient import TestClient


def test_nosniff_on_json_endpoint(client: TestClient) -> None:
    response = client.get("/v1/verses/John 3:16")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"


def test_nosniff_on_error_response(client: TestClient) -> None:
    response = client.get("/v1/verses/foo bar")  # 400 unparseable_reference
    assert response.status_code == 400
    assert response.headers["x-content-type-options"] == "nosniff"


def test_nosniff_on_docs(client: TestClient) -> None:
    response = client.get("/docs")  # vendored Swagger UI HTML
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
