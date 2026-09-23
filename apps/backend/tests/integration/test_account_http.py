"""HTTP and restart coverage for account ownership and session security."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from alpha_defense.application.shared import ResourceNotFoundError
from alpha_defense.bootstrap import build_container, create_http_app
from alpha_defense.transport.http.v1.dependencies import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
)
from alpha_defense.transport.http.v1.schemas import ObservationInputSchema
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings

PASSWORD = "synthetic-password-123"


def _command(client: TestClient, path: str, key: str, payload: dict[str, str]) -> object:
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None
    return client.post(
        path,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
        json=payload,
    )


def test_account_http_csrf_session_logout_and_secret_storage(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    database_path = tmp_path / "accounts.db"
    migrate(database_path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{database_path}")
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        account_service=container.account_service,
    )
    with (
        TestClient(app, raise_server_exceptions=False) as first,
        TestClient(
            app,
            raise_server_exceptions=False,
        ) as second,
    ):
        first.get("/api/v1/session")
        payload = {"login": "alice", "password": PASSWORD}
        assert (
            first.post(
                "/api/v1/accounts",
                headers={"Idempotency-Key": "no-csrf"},
                json=payload,
            ).status_code
            == 403
        )
        invalid_payload = first.post(
            "/api/v1/accounts",
            headers={
                "X-CSRF-Token": first.cookies[CSRF_COOKIE_NAME],
                "Idempotency-Key": "bad-body",
            },
            json={"login": "alice", "password": "S3cr!"},
        )
        assert invalid_payload.status_code == 422
        assert "S3cr!" not in invalid_payload.text
        registered = _command(first, "/api/v1/accounts", "register", payload)
        assert registered.status_code == 201
        assert registered.json()["auth_kind"] == "account"
        session_token = first.cookies.get(SESSION_COOKIE_NAME)
        assert session_token is not None
        assert first.get("/api/v1/session").json()["user_id"] == registered.json()["user_id"]

        second.get("/api/v1/session")
        invalid = _command(
            second,
            "/api/v1/sessions",
            "wrong",
            {
                "login": "alice",
                "password": "incorrect-pass-123",
            },
        )
        assert invalid.status_code == 401
        assert invalid.json()["code"] == "invalid_credentials"
        logged_in = _command(second, "/api/v1/sessions", "login", payload)
        assert logged_in.status_code == 201
        assert logged_in.json()["user_id"] == registered.json()["user_id"]
        assert logged_in.json()["namespace_id"] == registered.json()["namespace_id"]
        assert logged_in.json()["session_id"] != registered.json()["session_id"]

        csrf = first.cookies.get(CSRF_COOKIE_NAME)
        assert csrf is not None
        logout = first.post(
            "/api/v1/sessions/logout",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "logout"},
        )
        assert logout.status_code == 204
        first.cookies.set(SESSION_COOKIE_NAME, session_token)
        first.cookies.set(CSRF_COOKIE_NAME, csrf)
        replay = first.post(
            "/api/v1/sessions/logout",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "logout"},
        )
        assert replay.status_code == 204
        first.cookies.set(SESSION_COOKIE_NAME, session_token)
        assert first.get("/api/v1/session").json()["status"] == "anonymous"
        assert second.get("/api/v1/session").json()["status"] == "active"

    with container.engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT password_hash FROM accounts WHERE normalized_login = 'alice'")
        ).scalar_one()
        audit = " ".join(
            connection.execute(sa.text("SELECT payload_json FROM audit_events")).scalars()
        )
        idem = " ".join(
            connection.execute(
                sa.text("SELECT COALESCE(result_json, '') FROM idempotency_records")
            ).scalars()
        )
    container.close()
    assert row.startswith("$argon2id$")
    assert PASSWORD not in row + audit + idem
    assert session_token not in audit + idem
    assert PASSWORD not in caplog.text
    assert session_token not in caplog.text


def test_account_relogin_after_restart_restores_observation_and_excludes_other_owner(
    tmp_path: Path,
) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "restart.db"
    migrate(database_path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{database_path}")
    first = build_container(settings)
    pre = first.identity_service.bootstrap_session(session_token=None, pre_session_token=None)
    assert pre.pre_session_token is not None
    registered = first.account_service.register(
        pre_session_token=pre.pre_session_token,
        idempotency_key="register",
        login="alice",
        password=PASSWORD,
    )
    actor = first.identity_service.resolve_actor(registered.session_token)
    fixture = next(
        item for item in first.catalog.load().fixtures if item.fixture_id == "s01-card-block-sms"
    )
    payload = dict(fixture.payload)
    source = payload.pop("source")
    assert isinstance(source, str)
    observation_input = ObservationInputSchema.model_validate(payload).to_input()
    receipt = first.analyze_contact.execute(
        actor=actor,
        source=source,
        observation_input=observation_input,
    )
    first.close()

    restarted = build_container(settings)
    pre2 = restarted.identity_service.bootstrap_session(session_token=None, pre_session_token=None)
    assert pre2.pre_session_token is not None
    logged_in = restarted.account_service.login(
        pre_session_token=pre2.pre_session_token,
        idempotency_key="login",
        login="ALICE",
        password=PASSWORD,
    )
    second_actor = restarted.identity_service.resolve_actor(logged_in.session_token)
    restored = restarted.get_observation.execute(
        actor=second_actor,
        observation_id=receipt.observation.observation_id,
    )
    incident = restarted.get_incident.execute(
        actor=second_actor,
        incident_id=receipt.incident.incident_id,
    )
    attached = restarted.analyze_contact.execute(
        actor=second_actor,
        source=source,
        observation_input=replace(
            observation_input, source_event_id="same-conversation-next-event"
        ),
    )
    assert restored.observation_id == receipt.observation.observation_id
    assert incident.incident_id == receipt.incident.incident_id
    assert attached.incident.incident_id == receipt.incident.incident_id
    assert attached.incident.context_version == 2
    assert second_actor.session_id != actor.session_id
    assert second_actor.namespace_id == actor.namespace_id

    pre3 = restarted.identity_service.bootstrap_session(session_token=None, pre_session_token=None)
    assert pre3.pre_session_token is not None
    foreign = restarted.account_service.register(
        pre_session_token=pre3.pre_session_token,
        idempotency_key="foreign",
        login="bobby",
        password=PASSWORD,
    )
    with pytest.raises(ResourceNotFoundError):
        restarted.get_observation.execute(
            actor=restarted.identity_service.resolve_actor(foreign.session_token),
            observation_id=restored.observation_id,
        )
    with pytest.raises(ResourceNotFoundError):
        restarted.get_incident.execute(
            actor=restarted.identity_service.resolve_actor(foreign.session_token),
            incident_id=incident.incident_id,
        )
    restarted.close()


def test_login_http_returns_rate_limit_after_five_failures(tmp_path: Path) -> None:
    database_path = tmp_path / "limit.db"
    migrate(database_path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{database_path}")
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        account_service=container.account_service,
    )
    with TestClient(app) as registered, TestClient(app) as attempted:
        registered.get("/api/v1/session")
        assert (
            _command(
                registered,
                "/api/v1/accounts",
                "register",
                {
                    "login": "alice",
                    "password": PASSWORD,
                },
            ).status_code
            == 201
        )
        attempted.get("/api/v1/session")
        for index in range(5):
            response = _command(
                attempted,
                "/api/v1/sessions",
                f"wrong-{index}",
                {
                    "login": "alice",
                    "password": "incorrect-pass-123",
                },
            )
            assert response.status_code == 401
        blocked = _command(
            attempted,
            "/api/v1/sessions",
            "blocked",
            {
                "login": "alice",
                "password": PASSWORD,
            },
        )
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "rate_limited"
    container.close()
