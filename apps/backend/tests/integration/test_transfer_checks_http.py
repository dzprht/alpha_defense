"""P22 migrated HTTP check: evidence, ownership, replay, staleness and restart."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from alpha_defense.bootstrap import build_container, create_http_app
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import (
    IndicatorType,
    RegistrySnapshot,
    SourceVersion,
    ThreatIndicator,
    ThreatRecord,
    ThreatRecordStatus,
)
from alpha_defense.transport.http.v1.dependencies import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from tests.catalog_helpers import REPOSITORY_ROOT, install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def _post(client: TestClient, path: str, key: str, body: object) -> object:
    return client.post(
        path,
        headers={"X-CSRF-Token": client.cookies[CSRF_COOKIE_NAME], "Idempotency-Key": key},
        json=body,
    )


def _grant(client: TestClient, scope: str, key: str, revision: int = 0) -> None:
    response = client.patch(
        f"/api/v1/consents/{scope}",
        headers={"X-CSRF-Token": client.cookies[CSRF_COOKIE_NAME], "Idempotency-Key": key},
        json={"status": "granted", "expected_revision": revision},
    )
    assert response.status_code == 200, response.text


def _register(client: TestClient, login: str) -> None:
    client.get("/api/v1/session")
    response = _post(
        client,
        "/api/v1/accounts",
        f"register-{login}",
        {"login": login, "password": "synthetic-transfer-password"},
    )
    assert response.status_code == 201, response.text


def _publish_recipient_match(container: object, recipient_code: str) -> None:
    now = datetime.now(UTC)
    with container.unit_of_work() as uow:
        current = uow.threat_registry.get_current()
        assert current is not None
        source = current.source_versions[0].source
        record = ThreatRecord(
            source=source,
            source_record_id="p22-recipient-match",
            indicator=ThreatIndicator.from_raw(
                IndicatorType.ACCOUNT_TOKEN, f"demo-recipient:{recipient_code}"
            ),
            status=ThreatRecordStatus.ACTIVE,
            first_seen_at=now - timedelta(minutes=2),
            observed_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=10),
            evidence_ref="fixture://p22-recipient-match",
            verification_source="fixture.local",
        )
        snapshot = RegistrySnapshot(
            snapshot_id=EntityId(uuid4()),
            version="registry-p22-recipient-match",
            source_versions=(SourceVersion(source, "99.0.0"),),
            published_at=now,
            valid_until=now + timedelta(hours=1),
            records=(record,),
            content_sha256=sha256(b"p22-recipient-match").hexdigest(),
        )
        uow.threat_registry.publish(snapshot, expected_current_id=current.snapshot_id)
        uow.commit()


def test_transfer_check_http_evidence_staleness_scope_and_restart(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    path = tmp_path / "transfer-checks.db"
    migrate(path)
    settings = make_settings(
        tmp_path,
        database_url=f"sqlite:///{path}",
        policy_version="demo-risk-v2",
        model_root=REPOSITORY_ROOT / "artifacts/text",
    )
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        account_service=container.account_service,
        financial_profiles=container.financial_profiles,
        transfer_intents=container.transfer_intents,
        transfer_checks=container.transfer_checks,
        complete_contact=container.complete_contact,
    )
    with (
        TestClient(app, raise_server_exceptions=False) as owner,
        TestClient(app, raise_server_exceptions=False) as foreign,
    ):
        assert (
            owner.get("/api/v1/transfer-checks/00000000-0000-0000-0000-000000000001").status_code
            == 401
        )
        _register(owner, "check-owner")
        profile = _post(owner, "/api/v1/profiles", "regular-profile", {"template_code": "regular"})
        assert profile.status_code == 201, profile.text
        profile_id = profile.json()["profile_id"]
        body = {"profile_id": profile_id, "amount_minor": 100_000, "recipient_code": "family"}
        intent = _post(owner, "/api/v1/transfer-intents", "create-intent", body)
        assert intent.status_code == 201, intent.text
        intent_id = intent.json()["intent_id"]
        check_path = f"/api/v1/transfer-intents/{intent_id}/checks"
        check_body = {"expected_revision": 1, "linked_incident_id": None}
        assert _post(owner, check_path, "no-consent", check_body).status_code == 403
        _grant(owner, "use_transaction_history", "grant-history")
        assert owner.post(check_path, json=check_body).status_code == 403
        assert (
            owner.post(
                check_path,
                headers={"X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME]},
                json=check_body,
            ).status_code
            == 400
        )
        assert _post(owner, check_path, "bad-revision", {"expected_revision": 0}).status_code == 422
        missing_registry = _post(owner, check_path, "missing-registry", check_body)
        assert missing_registry.status_code == 201, missing_registry.text
        assert missing_registry.json()["decision"] == "hold"
        assert missing_registry.json()["completeness"] == "partial"
        assert missing_registry.json()["recipient_lookup"] == "unavailable"
        assert missing_registry.json()["fresh"]

        container.refresh_threat_registry.execute()
        assert not owner.get(
            f"/api/v1/transfer-checks/{missing_registry.json()['check_id']}"
        ).json()["fresh"]
        checked = _post(owner, check_path, "complete-check", check_body)
        assert checked.status_code == 201, checked.text
        first = checked.json()
        assert first["decision"] == "allow"
        assert first["completeness"] == "complete"
        assert first["recipient_lookup"] == "no_match"
        assert first["history_version"] == 1
        assert first["policy_version"] == "transfer-risk-v1"
        assert first["registry_version"]
        assert first["expires_at"]
        with container.unit_of_work() as uow:
            persisted = uow.transfer_checks.get(EntityId.from_string(first["check_id"]))
            current_intent = uow.transfer_intents.get(EntityId.from_string(intent_id))
            assert persisted is not None and current_intent is not None
            assert "check_expired" in persisted.stale_reasons(
                now=persisted.expires_at,
                intent=current_intent,
                history_version=persisted.history_version,
                consent_revision=persisted.consent_revision,
                ingress_epoch=persisted.ingress_epoch,
                analysis_pending=False,
                context_version=None,
                contact_assessment_id=None,
                registry_snapshot_id=persisted.registry_snapshot_id,
                catalog_policy_version=persisted.catalog_policy_version,
                latest_check_id=persisted.check_id,
            )
            assert "history_changed" in persisted.stale_reasons(
                now=persisted.checked_at,
                intent=current_intent,
                history_version=persisted.history_version + 1,
                consent_revision=persisted.consent_revision,
                ingress_epoch=persisted.ingress_epoch,
                analysis_pending=False,
                context_version=None,
                contact_assessment_id=None,
                registry_snapshot_id=persisted.registry_snapshot_id,
                catalog_policy_version=persisted.catalog_policy_version,
                latest_check_id=persisted.check_id,
            )
            assert "contact_context_changed" in persisted.stale_reasons(
                now=persisted.checked_at,
                intent=current_intent,
                history_version=persisted.history_version,
                consent_revision=persisted.consent_revision,
                ingress_epoch=persisted.ingress_epoch + 1,
                analysis_pending=False,
                context_version=None,
                contact_assessment_id=None,
                registry_snapshot_id=persisted.registry_snapshot_id,
                catalog_policy_version=persisted.catalog_policy_version,
                latest_check_id=persisted.check_id,
            )
        assert _post(owner, check_path, "complete-check", check_body).json() == first
        assert (
            _post(
                owner, check_path, "complete-check", {**check_body, "expected_revision": 2}
            ).status_code
            == 409
        )
        assert owner.get(f"/api/v1/transfer-intents/{intent_id}").json()["status"] == "checked"
        assert len(owner.get(check_path).json()["items"]) == 2

        confirm_intent = _post(
            owner,
            "/api/v1/transfer-intents",
            "confirm-intent",
            {**body, "amount_minor": 400_000},
        )
        assert confirm_intent.status_code == 201
        confirm = _post(
            owner,
            f"/api/v1/transfer-intents/{confirm_intent.json()['intent_id']}/checks",
            "confirm-check",
            check_body,
        )
        assert confirm.status_code == 201, confirm.text
        assert confirm.json()["decision"] == "confirm"
        assert confirm.json()["amount_is_outlier"]

        sparse = _post(owner, "/api/v1/profiles", "sparse-profile", {"template_code": "sparse"})
        assert sparse.status_code == 201
        sparse_intent = _post(
            owner,
            "/api/v1/transfer-intents",
            "sparse-intent",
            {
                "profile_id": sparse.json()["profile_id"],
                "amount_minor": 100_000,
                "recipient_code": "family",
            },
        )
        assert sparse_intent.status_code == 201
        insufficient = _post(
            owner,
            f"/api/v1/transfer-intents/{sparse_intent.json()['intent_id']}/checks",
            "sparse-check",
            check_body,
        )
        assert insufficient.status_code == 201, insufficient.text
        assert insufficient.json()["behavior_status"] == "insufficient_data"
        assert insufficient.json()["sample_size"] == 5
        assert insufficient.json()["decision"] == "hold"
        assert insufficient.json()["completeness"] == "partial"

        _register(foreign, "check-foreign")
        _grant(foreign, "use_transaction_history", "foreign-history")
        foreign_profile = _post(
            foreign, "/api/v1/profiles", "foreign-profile", {"template_code": "regular"}
        )
        assert foreign_profile.status_code == 201
        foreign_intent = _post(
            foreign,
            "/api/v1/transfer-intents",
            "foreign-intent",
            {**body, "profile_id": foreign_profile.json()["profile_id"]},
        )
        assert foreign_intent.status_code == 201
        assert foreign.get(f"/api/v1/transfer-checks/{first['check_id']}").status_code == 404
        assert foreign.get(check_path).status_code == 404
        assert _post(foreign, check_path, "foreign-check", check_body).status_code == 404

        _grant(owner, "analyze_communications", "grant-communications", revision=1)
        observation = _post(
            owner,
            "/api/v1/observations",
            "contact",
            {
                "kind": "sms",
                "source_event_id": "p22-contact",
                "occurred_at": datetime.now(UTC).isoformat(),
                "payload": {
                    "text": "Назовите пароль от личного кабинета",
                    "sender": "+79991234567",
                    "conversation_id": "p22-conversation",
                },
            },
        )
        assert observation.status_code == 201, observation.text
        incident_id = observation.json()["incident_id"]
        assert not owner.get(f"/api/v1/transfer-checks/{first['check_id']}").json()["fresh"]
        assert (
            _post(
                foreign,
                f"/api/v1/transfer-intents/{foreign_intent.json()['intent_id']}/checks",
                "foreign-incident",
                {**check_body, "linked_incident_id": incident_id},
            ).status_code
            == 404
        )
        with_contact = _post(
            owner, check_path, "linked-contact", {**check_body, "linked_incident_id": incident_id}
        )
        assert with_contact.status_code == 201, with_contact.text
        assert with_contact.json()["linked_incident_id"] == incident_id
        assert with_contact.json()["contact_assessment_id"]
        assert with_contact.json()["model_version"]
        assert (
            "check_superseded"
            in owner.get(f"/api/v1/transfer-checks/{first['check_id']}").json()["stale_reasons"]
        )

        _publish_recipient_match(container, "family")
        assert not owner.get(f"/api/v1/transfer-checks/{with_contact.json()['check_id']}").json()[
            "fresh"
        ]
        denied = _post(owner, check_path, "threat-match", check_body)
        assert denied.status_code == 201, denied.text
        assert denied.json()["decision"] == "deny"
        assert denied.json()["recipient_lookup"] == "match"
        assert denied.json()["expires_at"] <= denied.json()["registry_valid_until"]

        revise = owner.patch(
            f"/api/v1/transfer-intents/{intent_id}",
            headers={"X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME], "Idempotency-Key": "revise"},
            json={**body, "amount_minor": 200_000, "expected_revision": 1},
        )
        assert revise.status_code == 200, revise.text
        assert (
            "intent_changed"
            in owner.get(f"/api/v1/transfer-checks/{denied.json()['check_id']}").json()[
                "stale_reasons"
            ]
        )
        assert _post(owner, check_path, "stale-revision", check_body).status_code == 409
        revoked = owner.patch(
            "/api/v1/consents/use_transaction_history",
            headers={
                "X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME],
                "Idempotency-Key": "revoke-history",
            },
            json={"status": "revoked", "expected_revision": 2},
        )
        assert revoked.status_code == 200, revoked.text
        assert (
            "consent_changed"
            in owner.get(f"/api/v1/transfer-checks/{denied.json()['check_id']}").json()[
                "stale_reasons"
            ]
        )
        assert (
            _post(
                owner, check_path, "after-revocation", {**check_body, "expected_revision": 2}
            ).status_code
            == 403
        )
        token = owner.cookies[SESSION_COOKIE_NAME]

    with container.engine.connect() as connection:
        assert connection.execute(sa.text("SELECT COUNT(*) FROM transfer_checks")).scalar_one() == 6
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM demo_bank_results")).scalar_one() == 0
        )
    with container.engine.begin() as connection:
        try:
            connection.execute(sa.text("UPDATE transfer_checks SET snapshot = '{}'"))
        except SQLAlchemyError:
            pass
        else:
            raise AssertionError("SQLite must reject transfer check rewrites")
    with container.engine.begin() as connection:
        try:
            connection.execute(sa.text("DELETE FROM transfer_checks"))
        except SQLAlchemyError:
            pass
        else:
            raise AssertionError("SQLite must reject transfer check deletes")
    container.close()
    restarted = build_container(settings)
    resumed_app = create_http_app(
        readiness=restarted.readiness,
        identity_service=restarted.identity_service,
        transfer_checks=restarted.transfer_checks,
    )
    with TestClient(resumed_app, raise_server_exceptions=False) as resumed:
        resumed.cookies.set(SESSION_COOKIE_NAME, token)
        result = resumed.get(f"/api/v1/transfer-checks/{denied.json()['check_id']}")
        assert result.status_code == 200, result.text
        assert result.json()["decision"] == "deny"
        assert not result.json()["fresh"]
        assert resumed.get("/api/v1/health/ready").status_code == 200
    restarted.close()
