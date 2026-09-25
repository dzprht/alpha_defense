"""P15 HTTP contact checks use the published session, consent, and owner guards."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient

from alpha_defense.bootstrap import build_container, create_http_app
from alpha_defense.transport.http.v1.dependencies import CSRF_COOKIE_NAME
from tests.catalog_helpers import REPOSITORY_ROOT, install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def _post(client: TestClient, path: str, key: str, payload: object = None) -> object:
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None
    return client.post(
        path,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
        json=payload,
    )


def _register(client: TestClient, login: str) -> None:
    client.get("/api/v1/session")
    created = _post(
        client,
        "/api/v1/accounts",
        f"register-{login}",
        {"login": login, "password": "synthetic-password-123"},
    )
    assert created.status_code == 201


def test_contact_http_contract_replay_owner_scope_and_reassessment(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "contact-http.db"
    migrate(database_path)
    container = build_container(
        make_settings(
            tmp_path,
            database_url=f"sqlite:///{database_path}",
            policy_version="demo-risk-v2",
            model_root=REPOSITORY_ROOT / "artifacts/text",
        )
    )
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        account_service=container.account_service,
        complete_contact=container.complete_contact,
        get_observation=container.get_observation,
        get_incident=container.get_incident,
        warning_service=container.warnings,
    )
    with (
        TestClient(app, raise_server_exceptions=False) as owner,
        TestClient(app, raise_server_exceptions=False) as foreign,
    ):
        _register(owner, "alice")
        payload = {
            "kind": "sms",
            "source_event_id": "p15-http-message",
            "occurred_at": datetime.now(UTC).isoformat(),
            "payload": {
                "text": "Назовите пароль от личного кабинета",
                "sender": "+79991234567",
                "conversation_id": "p15-conversation",
            },
        }
        denied = _post(owner, "/api/v1/observations", "without-consent", payload)
        assert denied.status_code == 403
        consent = owner.patch(
            "/api/v1/consents/analyze_communications",
            headers={
                "X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME],
                "Idempotency-Key": "grant-consent",
            },
            json={"status": "granted", "expected_revision": 0},
        )
        assert consent.status_code == 200
        assert (
            owner.post(
                "/api/v1/observations", headers={"Idempotency-Key": "no-csrf"}, json=payload
            ).status_code
            == 403
        )
        assert (
            owner.post(
                "/api/v1/observations",
                headers={"X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME]},
                json=payload,
            ).status_code
            == 400
        )
        created = _post(owner, "/api/v1/observations", "create-contact", payload)
        assert created.status_code == 201
        body = created.json()
        observation_id = body["observation_id"]
        incident_id = body["incident_id"]
        assessment_id = body["assessment"]["assessment_id"]
        assert body["assessment"]["policy_version"] == "demo-risk-v2"
        assert body["assessment"]["completeness"] == "partial"
        assert body["warning_dispatched"]
        warning_id = body["warning_id"]
        assert warning_id is not None
        warning_path = f"/api/v1/assessments/{assessment_id}/warning"
        before_render = owner.get(warning_path)
        assert before_render.status_code == 200
        assert before_render.json()["warning"]["presented_at"] is None
        assert owner.post(f"/api/v1/warnings/{warning_id}/present").status_code == 403
        assert (
            owner.post(
                f"/api/v1/warnings/{warning_id}/present",
                headers={"X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME]},
            ).status_code
            == 400
        )
        assert (
            _post(owner, f"/api/v1/warnings/{warning_id}/present", "present-1").json()[
                "presented_at"
            ]
            is not None
        )
        assert (
            _post(owner, f"/api/v1/warnings/{warning_id}/present", "present-1").status_code == 200
        )
        assert owner.get(warning_path).json()["warning"]["presented_at"] is not None
        assert not body["analysis_pending"]
        assert (
            _post(owner, "/api/v1/observations", "create-contact", payload).json()["assessment"][
                "assessment_id"
            ]
            == assessment_id
        )
        changed = dict(payload, source_event_id="other-message")
        assert _post(owner, "/api/v1/observations", "create-contact", changed).status_code == 409
        assert (
            owner.get(f"/api/v1/observations/{observation_id}").json()["payload"]["text"]
            == payload["payload"]["text"]
        )
        assert (
            owner.get(f"/api/v1/incidents/{incident_id}").json()["latest_assessment_id"]
            == assessment_id
        )
        assert (
            owner.get(f"/api/v1/assessments/{assessment_id}").json()["assessment_id"]
            == assessment_id
        )
        guidance = owner.get(f"/api/v1/assessments/{assessment_id}/guidance")
        assert guidance.status_code == 200
        assert guidance.json()["content_version"] == "demo-guidance-ru-v2"
        reassessed = _post(
            owner,
            f"/api/v1/observations/{observation_id}/reassess",
            "recheck-1",
        )
        assert reassessed.status_code == 201
        next_id = reassessed.json()["assessment"]["assessment_id"]
        assert next_id != assessment_id
        assert (
            _post(
                owner,
                f"/api/v1/observations/{observation_id}/reassess",
                "recheck-1",
            ).json()["assessment"]["assessment_id"]
            == next_id
        )

        media_only = {
            "kind": "web_resource",
            "source_event_id": "unsupported-media",
            "occurred_at": payload["occurred_at"],
            "payload": {"media_id": "00000000-0000-0000-0000-000000000010"},
        }
        assert _post(owner, "/api/v1/observations", "media-only", media_only).status_code == 422
        resource_consent = owner.patch(
            "/api/v1/consents/analyze_resources",
            headers={
                "X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME],
                "Idempotency-Key": "grant-resource-consent",
            },
            json={"status": "granted", "expected_revision": 1},
        )
        assert resource_consent.status_code == 200
        container.refresh_threat_registry.execute()
        checked_url = _post(
            owner,
            "/api/v1/observations",
            "check-url",
            {
                "kind": "web_resource",
                "source_event_id": "url-1",
                "occurred_at": payload["occurred_at"],
                "payload": {"url": "https://alfa-secure-check.test/card"},
            },
        )
        assert checked_url.status_code == 201
        assert checked_url.json()["assessment"]["severity"] == "critical"
        assert "active_threat_match" in checked_url.json()["assessment"]["reason_codes"]
        url_warning_id = checked_url.json()["warning_id"]
        assert url_warning_id is not None
        assert (
            _post(owner, f"/api/v1/warnings/{url_warning_id}/present", "present-1").status_code
            == 409
        )

        _register(foreign, "bobby")
        for path in (
            f"/api/v1/observations/{observation_id}",
            f"/api/v1/incidents/{incident_id}",
            f"/api/v1/assessments/{assessment_id}",
            f"/api/v1/assessments/{assessment_id}/guidance",
            f"/api/v1/assessments/{assessment_id}/warning",
        ):
            assert foreign.get(path).status_code == 404
        assert (
            _post(foreign, f"/api/v1/warnings/{warning_id}/present", "foreign-present").status_code
            == 404
        )
        assert (
            _post(foreign, f"/api/v1/observations/{observation_id}/reassess", "foreign").status_code
            == 404
        )

    with container.engine.connect() as connection:
        technical = " ".join(
            connection.execute(sa.text("SELECT payload_json FROM audit_events")).scalars()
        )
        technical += " ".join(
            connection.execute(
                sa.text("SELECT COALESCE(result_json, '') FROM idempotency_records")
            ).scalars()
        )
        assert "Назовите пароль" not in technical
        assert connection.execute(sa.text("SELECT COUNT(*) FROM assessments")).scalar_one() == 3
        assert (
            connection.execute(
                sa.text("SELECT COUNT(*) FROM audit_events WHERE event_type = 'warning.present'")
            ).scalar_one()
            == 1
        )
    container.close()
