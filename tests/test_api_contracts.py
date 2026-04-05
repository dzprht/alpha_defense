"""Contract and smoke tests for the FastAPI skeleton."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from alpha_protect.presentation.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def assert_not_implemented_payload(payload: dict[str, object]) -> None:
    assert set(payload) == {"request_id", "status", "detail", "timestamp"}
    assert payload["status"] == "not_implemented"
    UUID(str(payload["request_id"]))
    datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_endpoint(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


POST_ENDPOINT_CASES = [
    ("/api/v1/signals/text/analyze", {"text": "help me transfer now"}),
    ("/api/v1/signals/url/check", {"url": "https://example.com/login"}),
    (
        "/api/v1/signals/behavior/anomaly",
        {"user_id": "user-1", "event_type": "transfer", "amount": 150000.0},
    ),
    (
        "/api/v1/calls/alfa-id/verify",
        {"phone_number": "+79991234567", "claimed_source": "alfa_bank"},
    ),
    (
        "/api/v1/intel/open-banking/check",
        {"operation_id": "op-1", "user_id": "user-1", "amount": 1000.0},
    ),
    (
        "/api/v1/intel/gov/check",
        {"indicator": "suspicious-domain.test", "indicator_type": "domain"},
    ),
    ("/api/v1/intel/operator/check", {"phone_number": "+79991234567"}),
    (
        "/api/v1/registry/threats/upsert",
        {"indicator": "https://fake-bank.test", "indicator_type": "url", "source": "api"},
    ),
    (
        "/api/v1/responses/transaction/block",
        {"operation_id": "op-2", "reason": "suspected fraud"},
    ),
    (
        "/api/v1/responses/resource/block",
        {
            "resource": "https://fake-bank.test",
            "resource_type": "url",
            "reason": "phishing",
        },
    ),
    (
        "/api/v1/responses/user/alert",
        {"user_id": "user-1", "message": "Suspicious activity", "channel": "push"},
    ),
    (
        "/api/v1/awareness/hint",
        {"user_id": "user-1", "context": "unknown caller asks for transfer"},
    ),
]


@pytest.mark.parametrize(("path", "payload"), POST_ENDPOINT_CASES)
def test_antifraud_post_endpoints_return_501(
    client: TestClient,
    path: str,
    payload: dict[str, object],
) -> None:
    response = client.post(path, json=payload)
    assert response.status_code == 501
    assert_not_implemented_payload(response.json())


@pytest.mark.parametrize("path", [case[0] for case in POST_ENDPOINT_CASES])
def test_antifraud_post_endpoints_validate_payload(client: TestClient, path: str) -> None:
    response = client.post(path, json={})
    assert response.status_code == 422


def test_registry_get_endpoint_returns_501(client: TestClient) -> None:
    response = client.get("/api/v1/registry/threats/example.com")
    assert response.status_code == 501
    assert_not_implemented_payload(response.json())


def test_openapi_contains_expected_paths_and_tags(client: TestClient) -> None:
    docs_response = client.get("/docs")
    assert docs_response.status_code == 200

    openapi_schema = client.get("/openapi.json")
    assert openapi_schema.status_code == 200
    schema = openapi_schema.json()

    expected_paths = [
        "/health",
        "/ready",
        "/api/v1/signals/text/analyze",
        "/api/v1/signals/url/check",
        "/api/v1/signals/behavior/anomaly",
        "/api/v1/calls/alfa-id/verify",
        "/api/v1/intel/open-banking/check",
        "/api/v1/intel/gov/check",
        "/api/v1/intel/operator/check",
        "/api/v1/registry/threats/upsert",
        "/api/v1/registry/threats/{indicator}",
        "/api/v1/responses/transaction/block",
        "/api/v1/responses/resource/block",
        "/api/v1/responses/user/alert",
        "/api/v1/awareness/hint",
    ]

    for path in expected_paths:
        assert path in schema["paths"]

    expected_tags_by_operation = {
        ("/health", "get"): "system",
        ("/ready", "get"): "system",
        ("/api/v1/signals/text/analyze", "post"): "signals",
        ("/api/v1/signals/url/check", "post"): "signals",
        ("/api/v1/signals/behavior/anomaly", "post"): "signals",
        ("/api/v1/calls/alfa-id/verify", "post"): "signals",
        ("/api/v1/intel/open-banking/check", "post"): "intel",
        ("/api/v1/intel/gov/check", "post"): "intel",
        ("/api/v1/intel/operator/check", "post"): "intel",
        ("/api/v1/registry/threats/upsert", "post"): "registry",
        ("/api/v1/registry/threats/{indicator}", "get"): "registry",
        ("/api/v1/responses/transaction/block", "post"): "responses",
        ("/api/v1/responses/resource/block", "post"): "responses",
        ("/api/v1/responses/user/alert", "post"): "responses",
        ("/api/v1/awareness/hint", "post"): "awareness",
    }

    for (path, method), tag in expected_tags_by_operation.items():
        operation = schema["paths"][path][method]
        assert operation["tags"] == [tag]
