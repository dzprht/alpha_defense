"""Cookie, CSRF, idempotency, restart, and consent HTTP scenarios."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from alpha_defense.application.shared import (
    ActionForbiddenError,
    ActorContext,
    ActorRole,
    ResourceNotFoundError,
)
from alpha_defense.bootstrap import build_container, create_http_app
from alpha_defense.domain.shared import ExecutionMode
from alpha_defense.transport.http.v1.dependencies import (
    CSRF_COOKIE_NAME,
    PRE_SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    require_namespace,
    require_owner,
    require_role,
)
from tests.contract.test_uow_contract import entity_id, migrate
from tests.unit.test_settings import make_settings


@pytest.fixture
def identity_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    database_path = tmp_path / "identity-http.db"
    migrate(database_path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{database_path}")
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        cors_origins=settings.cors_origins,
        allowed_hosts=settings.allowed_hosts,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, database_path
    container.close()


def _start_session(
    client: TestClient,
    *,
    key: str = "start-session",
) -> tuple[dict[str, object], str, str]:
    anonymous = client.get("/api/v1/session")
    pre_session_token = client.cookies.get(PRE_SESSION_COOKIE_NAME)
    csrf_token = client.cookies.get(CSRF_COOKIE_NAME)
    assert pre_session_token is not None
    assert csrf_token is not None
    created = client.post(
        "/api/v1/sessions/demo",
        headers={"X-CSRF-Token": csrf_token, "Idempotency-Key": key},
        json={"profile_code": "demo-user"},
    )
    assert anonymous.status_code == 200
    assert created.status_code == 201
    return created.json(), pre_session_token, csrf_token


def test_session_is_server_scoped_replayable_and_persisted(
    identity_client: tuple[TestClient, Path],
) -> None:
    client, database_path = identity_client
    anonymous = client.get("/api/v1/session")
    cookies = anonymous.headers.get_list("set-cookie")
    assert anonymous.json()["status"] == "anonymous"
    assert any(PRE_SESSION_COOKIE_NAME in value and "HttpOnly" in value for value in cookies)
    assert any(CSRF_COOKIE_NAME in value and "HttpOnly" not in value for value in cookies)
    pre_session_token = client.cookies.get(PRE_SESSION_COOKIE_NAME)
    pre_session_csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert pre_session_token is not None
    assert pre_session_csrf is not None

    created = client.post(
        "/api/v1/sessions/demo",
        headers={"X-CSRF-Token": pre_session_csrf, "Idempotency-Key": "start-one"},
        json={"profile_code": "demo-user"},
    )
    body = created.json()
    assert created.status_code == 201
    assert body["roles"] == ["demo_user"]
    assert body["user_id"] != body["namespace_id"]
    assert body["consent_revision"] == 0
    assert len(body["consents"]) == 5
    assert {item["status"] for item in body["consents"]} == {"revoked"}
    session_token = client.cookies.get(SESSION_COOKIE_NAME)
    assert session_token is not None
    assert client.cookies.get(PRE_SESSION_COOKIE_NAME) is None

    active = client.get("/api/v1/session")
    assert active.status_code == 200
    assert active.json()["session_id"] == body["session_id"]

    client.cookies.set(PRE_SESSION_COOKIE_NAME, pre_session_token)
    client.cookies.set(CSRF_COOKIE_NAME, pre_session_csrf)
    replayed = client.post(
        "/api/v1/sessions/demo",
        headers={"X-CSRF-Token": pre_session_csrf, "Idempotency-Key": "start-one"},
        json={"profile_code": "demo-user"},
    )
    assert replayed.status_code == 201
    assert replayed.json()["session_id"] == body["session_id"]

    client.cookies.set(PRE_SESSION_COOKIE_NAME, pre_session_token)
    client.cookies.set(CSRF_COOKIE_NAME, pre_session_csrf)
    conflicting = client.post(
        "/api/v1/sessions/demo",
        headers={"X-CSRF-Token": pre_session_csrf, "Idempotency-Key": "start-one"},
        json={"profile_code": "demo-senior"},
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["code"] == "idempotency_conflict"

    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM users")).scalar_one() == 1
        assert connection.execute(sa.text("SELECT count(*) FROM sessions")).scalar_one() == 1
        assert connection.execute(sa.text("SELECT count(*) FROM consents")).scalar_one() == 5
        stored_pre = connection.execute(
            sa.text("SELECT token_fingerprint FROM pre_sessions")
        ).scalar_one()
        stored_session = connection.execute(
            sa.text("SELECT token_fingerprint FROM sessions")
        ).scalar_one()
        assert pre_session_token not in {stored_pre, stored_session}
        assert session_token not in {stored_pre, stored_session}
    engine.dispose()


def test_session_commands_enforce_csrf_idempotency_and_server_roles(
    identity_client: tuple[TestClient, Path],
) -> None:
    client, _ = identity_client
    anonymous = client.get("/api/v1/session")
    assert anonymous.status_code == 200
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None

    no_csrf = client.post(
        "/api/v1/sessions/demo",
        headers={"Idempotency-Key": "missing-csrf"},
        json={"profile_code": "demo-user"},
    )
    no_key = client.post(
        "/api/v1/sessions/demo",
        headers={"X-CSRF-Token": csrf},
        json={"profile_code": "demo-user"},
    )
    escalated = client.post(
        "/api/v1/sessions/demo",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "role-escalation"},
        json={"profile_code": "demo-user", "roles": ["researcher"]},
    )

    assert no_csrf.status_code == 403
    assert no_csrf.json()["code"] == "csrf_failed"
    assert no_key.status_code == 400
    assert no_key.json()["code"] == "idempotency_key_required"
    assert escalated.status_code == 422
    assert escalated.json()["code"] == "validation_failed"


def test_consent_revoke_advances_revision_without_disabling_base_session(
    identity_client: tuple[TestClient, Path],
) -> None:
    client, _ = identity_client
    session, _, _ = _start_session(client)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None

    grant = client.patch(
        "/api/v1/consents/participate_in_research",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "grant-research"},
        json={"status": "granted", "expected_revision": 0},
    )
    revoke = client.patch(
        "/api/v1/consents/participate_in_research",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "revoke-research"},
        json={"status": "revoked", "expected_revision": 1},
    )
    repeated_revoke = client.patch(
        "/api/v1/consents/participate_in_research",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "revoke-research"},
        json={"status": "revoked", "expected_revision": 1},
    )
    stale = client.patch(
        "/api/v1/consents/send_notifications",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "stale-consent"},
        json={"status": "granted", "expected_revision": 1},
    )
    restored = client.get("/api/v1/session")

    assert grant.status_code == 200
    assert grant.json()["revision"] == 1
    assert revoke.status_code == 200
    assert revoke.json()["revision"] == 2
    assert repeated_revoke.json() == revoke.json()
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_revision"
    assert restored.status_code == 200
    assert restored.json()["session_id"] == session["session_id"]
    assert restored.json()["consent_revision"] == 2
    assert restored.json()["capabilities"] == ["update_consents"]


def test_session_survives_process_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "restart-session.db"
    migrate(database_path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{database_path}")
    first_container = build_container(settings)
    first_app = create_http_app(
        readiness=first_container.readiness,
        identity_service=first_container.identity_service,
    )
    with TestClient(first_app) as first_client:
        created, _, _ = _start_session(first_client)
        session_token = first_client.cookies.get(SESSION_COOKIE_NAME)
    first_container.close()
    assert session_token is not None

    second_container = build_container(settings)
    second_app = create_http_app(
        readiness=second_container.readiness,
        identity_service=second_container.identity_service,
    )
    with TestClient(second_app) as second_client:
        second_client.cookies.set(SESSION_COOKIE_NAME, session_token)
        restored = second_client.get("/api/v1/session")
    second_container.close()

    assert restored.status_code == 200
    assert restored.json()["session_id"] == created["session_id"]


def test_owner_namespace_and_role_guards_hide_foreign_resources() -> None:
    actor = ActorContext(
        user_id=entity_id(1),
        session_id=entity_id(2),
        namespace_id=entity_id(3),
        roles=frozenset({ActorRole.DEMO_USER}),
        consent_revision=0,
        execution_mode=ExecutionMode.MOCK,
    )

    require_owner(actor, str(actor.user_id))
    require_namespace(actor, str(actor.namespace_id))
    require_role(actor, ActorRole.DEMO_USER)
    with pytest.raises(ResourceNotFoundError):
        require_owner(actor, str(entity_id(4)))
    with pytest.raises(ResourceNotFoundError):
        require_namespace(actor, str(entity_id(5)))
    with pytest.raises(ActionForbiddenError):
        require_role(actor, ActorRole.RESEARCHER)
