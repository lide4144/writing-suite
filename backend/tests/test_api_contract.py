from __future__ import annotations

from fastapi.testclient import TestClient

from novel_agent.main import create_app


def test_m1_openapi_routes_have_unique_operation_ids() -> None:
    app = create_app()
    operation_ids = [
        operation["operationId"]
        for path in app.openapi()["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert "/api/v1/projects" in app.openapi()["paths"]
    assert "/api/v1/presets" in app.openapi()["paths"]


def test_validation_errors_use_spec_error_shape() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/projects", json={"name": ""})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    assert payload["error"]["request_id"].startswith("req_")
    assert response.headers["x-request-id"] == payload["error"]["request_id"]
