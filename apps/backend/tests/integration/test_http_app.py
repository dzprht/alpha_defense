"""Executable bootstrap and HTTP boundary integration checks."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alpha_defense.application.shared import ServiceUnavailableError
from alpha_defense.bootstrap import ConfigurationError, build_container, create_app, create_http_app
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


@pytest.fixture
def configured_app(tmp_path: Path) -> Iterator[tuple[TestClient, Path, str]]:
    database_path = tmp_path / "app.db"
    migrate(database_path)
    secret = "integration-secret-that-must-not-leak"
    settings = make_settings(tmp_path, session_secret=secret)
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        max_request_body_bytes=1024,
        cors_origins=settings.cors_origins,
        allowed_hosts=settings.allowed_hosts,
    )

    @app.get("/test/unavailable")
    async def unavailable() -> None:
        raise ServiceUnavailableError(f"storage failed: {secret} at {database_path}")

    @app.get("/test/crash")
    async def crash() -> None:
        raise RuntimeError(f"secret={secret}; database={database_path}")

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, database_path, secret
    container.close()


def test_valid_bootstrap_serves_liveness_but_not_incomplete_readiness(
    configured_app: tuple[TestClient, Path, str],
) -> None:
    client, database_path, secret = configured_app
    supplied_request_id = "00000000-0000-4000-8000-000000000123"

    live = client.get("/api/v1/health/live", headers={"X-Request-ID": supplied_request_id})
    ready = client.get("/api/v1/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "alive", "request_id": supplied_request_id}
    assert live.headers["X-Request-ID"] == supplied_request_id
    assert live.headers["X-Content-Type-Options"] == "nosniff"
    assert ready.status_code == 503
    assert ready.headers["content-type"].startswith("application/problem+json")
    assert ready.json()["code"] == "service_unavailable"
    assert ready.json()["retryable"] is True
    rendered = ready.text
    assert str(database_path) not in rendered
    assert secret not in rendered


def test_environment_factory_starts_with_valid_local_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "app.db"
    migrate(database_path)
    settings = make_settings(tmp_path)
    for field_name in type(settings).model_fields:
        value = getattr(settings, field_name)
        if field_name == "session_secret":
            rendered = value.get_secret_value()
        elif hasattr(value, "value"):
            rendered = value.value
        else:
            rendered = str(value)
        monkeypatch.setenv(field_name.upper(), rendered)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200


def test_invalid_request_id_is_replaced(configured_app: tuple[TestClient, Path, str]) -> None:
    client, _, _ = configured_app

    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "not-a-uuid"})

    generated = response.headers["X-Request-ID"]
    assert response.status_code == 200
    assert generated != "not-a-uuid"
    assert response.json()["request_id"] == generated


def test_untrusted_host_uses_problem_details(
    configured_app: tuple[TestClient, Path, str],
) -> None:
    client, _, _ = configured_app

    response = client.get("/api/v1/health/live", headers={"Host": "untrusted.example"})

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_host"


def test_body_limit_rejects_before_route_dispatch(
    configured_app: tuple[TestClient, Path, str],
) -> None:
    client, _, _ = configured_app

    response = client.post("/not-implemented", content=b"x" * 1025)

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "payload_too_large"


@pytest.mark.parametrize("path", ["/test/unavailable", "/test/crash"])
def test_internal_failures_do_not_expose_secret_or_database_path(
    configured_app: tuple[TestClient, Path, str],
    path: str,
) -> None:
    client, database_path, secret = configured_app

    response = client.get(path)

    assert response.status_code in {500, 503}
    assert response.headers["content-type"].startswith("application/problem+json")
    assert secret not in response.text
    assert str(database_path) not in response.text


def test_unmigrated_database_fails_startup(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    database_path.touch()
    settings = make_settings(tmp_path)

    with pytest.raises(ConfigurationError, match="managed schema"):
        build_container(settings)
