"""P23 real SQLite HTTP flow: permission, freshness, one effect, and cancellation."""

from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient
from httpx import Response
from pytest import MonkeyPatch

from alpha_defense.bootstrap import build_container, create_http_app
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.persistence.sqlalchemy.repositories import (
    SqlAlchemyAuditRepository,
)
from alpha_defense.transport.http.v1.dependencies import CSRF_COOKIE_NAME
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def _post(client: TestClient, path: str, key: str, body: object) -> Response:
    return client.post(
        path,
        headers={"X-CSRF-Token": client.cookies[CSRF_COOKIE_NAME], "Idempotency-Key": key},
        json=body,
    )


def _register(client: TestClient, login: str) -> None:
    client.get("/api/v1/session")
    response = _post(
        client,
        "/api/v1/accounts",
        f"register-{login}",
        {"login": login, "password": "synthetic-transfer-password"},
    )
    assert response.status_code == 201, response.text


def _grant(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/consents/use_transaction_history",
        headers={"X-CSRF-Token": client.cookies[CSRF_COOKIE_NAME], "Idempotency-Key": "grant"},
        json={"status": "granted", "expected_revision": 0},
    )
    assert response.status_code == 200, response.text


def test_execute_and_cancel_are_owner_scoped_atomic_and_replay_safe(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_valid_catalog(tmp_path)
    path = tmp_path / "completion.db"
    migrate(path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{path}")
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        account_service=container.account_service,
        financial_profiles=container.financial_profiles,
        transfer_intents=container.transfer_intents,
        transfer_checks=container.transfer_checks,
        complete_transfer=container.complete_transfer,
    )
    with (
        TestClient(app, raise_server_exceptions=False) as owner,
        TestClient(app, raise_server_exceptions=False) as foreign,
    ):
        _register(owner, "completion-owner")
        _register(foreign, "completion-foreign")
        profile = _post(owner, "/api/v1/profiles", "profile", {"template_code": "regular"})
        assert profile.status_code == 201, profile.text
        profile_id = profile.json()["profile_id"]
        body = {"profile_id": profile_id, "amount_minor": 100_000, "recipient_code": "family"}
        intent = _post(owner, "/api/v1/transfer-intents", "intent", body)
        assert intent.status_code == 201, intent.text
        intent_id = intent.json()["intent_id"]
        execute_path = f"/api/v1/transfer-intents/{intent_id}/execute"
        cancel_path = f"/api/v1/transfer-intents/{intent_id}/cancel"
        guard_body = {
            "check_id": intent_id,
            "expected_revision": 1,
            "acknowledge_warning": True,
        }
        assert owner.post(execute_path, json=guard_body).status_code == 403
        assert (
            _post(
                foreign,
                execute_path,
                "foreign",
                {
                    "check_id": intent_id,
                    "expected_revision": 1,
                    "acknowledge_warning": True,
                },
            ).status_code
            == 404
        )
        assert _post(owner, execute_path, "direct", guard_body).status_code == 409
        _grant(owner)
        incomplete = _post(
            owner,
            f"/api/v1/transfer-intents/{intent_id}/checks",
            "incomplete",
            {"expected_revision": 1},
        )
        assert incomplete.status_code == 201, incomplete.text
        assert incomplete.json()["decision"] == "hold"
        assert (
            _post(
                owner,
                execute_path,
                "held",
                {
                    "check_id": incomplete.json()["check_id"],
                    "expected_revision": 1,
                    "acknowledge_warning": True,
                },
            ).status_code
            == 403
        )
        container.refresh_threat_registry.execute()
        checked = _post(
            owner,
            f"/api/v1/transfer-intents/{intent_id}/checks",
            "allowed",
            {"expected_revision": 1},
        )
        assert checked.status_code == 201, checked.text
        assert checked.json()["decision"] == "allow"
        assert (
            _post(
                owner,
                execute_path,
                "superseded",
                {
                    "check_id": incomplete.json()["check_id"],
                    "expected_revision": 1,
                    "acknowledge_warning": True,
                },
            ).status_code
            == 409
        )
        command = {
            "check_id": checked.json()["check_id"],
            "expected_revision": 1,
            "acknowledge_warning": False,
        }
        assert (
            _post(owner, execute_path, "bad-shape", {**command, "decision": "allow"}).status_code
            == 422
        )
        with monkeypatch.context() as patch:

            def failed_audit(self: SqlAlchemyAuditRepository, record: object) -> None:
                raise RuntimeError("synthetic crash before commit")

            patch.setattr(SqlAlchemyAuditRepository, "append", failed_audit)
            assert _post(owner, execute_path, "execute", command).status_code == 500
        assert owner.get(f"/api/v1/transfer-intents/{intent_id}").json()["status"] == "checked"
        assert owner.get(f"/api/v1/profiles/{profile_id}").json()["history_version"] == 1
        with container.engine.connect() as connection:
            assert (
                connection.execute(
                    sa.text("SELECT COUNT(*) FROM demo_bank_results WHERE intent_id = :intent_id"),
                    {"intent_id": intent_id},
                ).scalar_one()
                == 0
            )
        executed = _post(owner, execute_path, "execute", command)
        assert executed.status_code == 200, executed.text
        first = executed.json()
        assert first["intent"]["status"] == "executed"
        assert first["operation_id"]
        assert first["execution_mode"] == "mock"
        assert _post(owner, execute_path, "execute", command).json() == first
        assert _post(owner, execute_path, "other-tab", command).json() == first
        assert (
            _post(
                owner, execute_path, "execute", {**command, "acknowledge_warning": True}
            ).status_code
            == 409
        )
        assert _post(owner, cancel_path, "too-late", {"expected_revision": 1}).status_code == 403
        history = owner.get(f"/api/v1/profiles/{profile_id}").json()
        assert history["history_version"] == 2
        assert [item["operation_id"] for item in history["operations"]].count(
            first["operation_id"]
        ) == 1
        assert len(history["operations"]) == len(profile.json()["operations"]) + 1
        with container.engine.connect() as connection:
            assert (
                connection.execute(
                    sa.text("SELECT COUNT(*) FROM demo_bank_results WHERE intent_id = :intent_id"),
                    {"intent_id": intent_id},
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM audit_events "
                        "WHERE aggregate_id = :intent_id "
                        "AND event_type = 'transfer.intent.executed'"
                    ),
                    {"intent_id": intent_id},
                ).scalar_one()
                == 1
            )

        confirm_intent = _post(
            owner,
            "/api/v1/transfer-intents",
            "confirm-intent",
            {
                **body,
                "amount_minor": 400_000,
            },
        )
        assert confirm_intent.status_code == 201
        confirm_id = confirm_intent.json()["intent_id"]
        confirm_check = _post(
            owner,
            f"/api/v1/transfer-intents/{confirm_id}/checks",
            "confirm-check",
            {"expected_revision": 1},
        )
        assert confirm_check.status_code == 201, confirm_check.text
        assert confirm_check.json()["decision"] == "confirm"
        confirm_command = {
            "check_id": confirm_check.json()["check_id"],
            "expected_revision": 1,
            "acknowledge_warning": False,
        }
        assert (
            _post(
                owner, f"/api/v1/transfer-intents/{confirm_id}/execute", "no-ack", confirm_command
            ).status_code
            == 403
        )
        assert (
            _post(
                owner,
                f"/api/v1/transfer-intents/{confirm_id}/execute",
                "ack",
                {
                    **confirm_command,
                    "acknowledge_warning": True,
                },
            ).status_code
            == 200
        )

        cancelled_intent = _post(owner, "/api/v1/transfer-intents", "cancel-intent", body)
        cancelled_id = cancelled_intent.json()["intent_id"]
        cancelled_path = f"/api/v1/transfer-intents/{cancelled_id}/cancel"
        assert (
            _post(foreign, cancelled_path, "foreign-cancel", {"expected_revision": 1}).status_code
            == 404
        )
        cancelled = _post(owner, cancelled_path, "cancel", {"expected_revision": 1})
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["intent"]["status"] == "cancelled"
        assert cancelled.json()["operation_id"] is None
        assert (
            _post(owner, cancelled_path, "cancel", {"expected_revision": 1}).json()
            == cancelled.json()
        )
        assert (
            _post(owner, cancelled_path, "other-cancel", {"expected_revision": 1}).json()
            == cancelled.json()
        )
        assert (
            _post(
                owner,
                f"/api/v1/transfer-intents/{cancelled_id}/execute",
                "cancelled-execute",
                {
                    "check_id": checked.json()["check_id"],
                    "expected_revision": 1,
                    "acknowledge_warning": True,
                },
            ).status_code
            == 409
        )
    container.close()
    restarted = build_container(settings)
    with restarted.unit_of_work() as uow:
        saved_intent = uow.transfer_intents.get(EntityId.from_string(intent_id))
        saved_result = uow.demo_bank.get_by_intent(EntityId.from_string(intent_id))
        saved_profile = uow.profiles.get(EntityId.from_string(profile_id))
        assert saved_intent is not None and saved_intent.status.value == "executed"
        assert saved_result is not None and str(saved_result.operation_id) == first["operation_id"]
        assert saved_profile is not None
        assert (
            sum(item.operation_id == saved_result.operation_id for item in saved_profile.operations)
            == 1
        )
    restarted.close()
