"""P21 real migrated HTTP draft flow, owner guards, and restart."""

from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient

from alpha_defense.bootstrap import build_container, create_http_app
from alpha_defense.transport.http.v1.dependencies import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def _post(client: TestClient, path: str, key: str, body: object) -> object:
    return client.post(
        path,
        headers={
            "X-CSRF-Token": client.cookies[CSRF_COOKIE_NAME],
            "Idempotency-Key": key,
        },
        json=body,
    )


def _patch(client: TestClient, path: str, key: str, body: object) -> object:
    return client.patch(
        path,
        headers={
            "X-CSRF-Token": client.cookies[CSRF_COOKIE_NAME],
            "Idempotency-Key": key,
        },
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
    assert response.status_code == 201


def test_transfer_draft_http_replay_owner_revision_and_restart(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    path = tmp_path / "transfer-intents.db"
    migrate(path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{path}")
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        account_service=container.account_service,
        financial_profiles=container.financial_profiles,
        transfer_intents=container.transfer_intents,
    )
    with (
        TestClient(app, raise_server_exceptions=False) as owner,
        TestClient(app, raise_server_exceptions=False) as foreign,
        TestClient(app, raise_server_exceptions=False) as same_account,
    ):
        assert owner.get("/api/v1/transfer-intents").status_code == 401
        _register(owner, "draft-owner")
        profile = _post(owner, "/api/v1/profiles", "regular-profile", {"template_code": "regular"})
        assert profile.status_code == 201
        profile_id = profile.json()["profile_id"]
        body = {"profile_id": profile_id, "amount_minor": 150_000, "recipient_code": "family"}
        assert (
            _post(
                owner,
                "/api/v1/transfer-intents",
                "fake-owner",
                {**body, "owner_id": "not-a-server-identity"},
            ).status_code
            == 422
        )
        assert owner.post("/api/v1/transfer-intents", json=body).status_code == 403
        assert (
            owner.post(
                "/api/v1/transfer-intents",
                headers={"X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME]},
                json=body,
            ).status_code
            == 400
        )
        assert (
            _post(owner, "/api/v1/transfer-intents", "bad", {**body, "amount_minor": 0}).status_code
            == 422
        )
        created = _post(owner, "/api/v1/transfer-intents", "create-draft", body)
        assert created.status_code == 201
        first = created.json()
        intent_id = first["intent_id"]
        assert first["status"] == "draft"
        assert first["revision"] == 1
        assert first["execution_mode"] == "mock"
        assert _post(owner, "/api/v1/transfer-intents", "create-draft", body).json() == first
        assert (
            _post(
                owner, "/api/v1/transfer-intents", "create-draft", {**body, "amount_minor": 1}
            ).status_code
            == 409
        )
        assert owner.get(f"/api/v1/transfer-intents/{intent_id}").json() == first
        assert owner.get("/api/v1/transfer-intents").json()["items"] == [first]

        revise = {**body, "amount_minor": 200_000, "expected_revision": 1}
        assert owner.patch(f"/api/v1/transfer-intents/{intent_id}", json=revise).status_code == 403
        assert (
            owner.patch(
                f"/api/v1/transfer-intents/{intent_id}",
                headers={"X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME]},
                json=revise,
            ).status_code
            == 400
        )
        changed = _patch(owner, f"/api/v1/transfer-intents/{intent_id}", "amount-change", revise)
        assert changed.status_code == 200
        second = changed.json()
        assert second["revision"] == 2
        assert second["fingerprint"] != first["fingerprint"]
        assert (
            _patch(owner, f"/api/v1/transfer-intents/{intent_id}", "amount-change", revise).json()
            == second
        )
        assert (
            _patch(
                owner, f"/api/v1/transfer-intents/{intent_id}", "stale-change", revise
            ).status_code
            == 409
        )
        recipient_change = {**revise, "recipient_code": "new-payee", "expected_revision": 2}
        third_response = _patch(
            owner, f"/api/v1/transfer-intents/{intent_id}", "recipient-change", recipient_change
        )
        assert third_response.status_code == 200
        third = third_response.json()
        assert third["revision"] == 3
        assert third["fingerprint"] != second["fingerprint"]
        assert (
            _patch(owner, f"/api/v1/transfer-intents/{intent_id}", "amount-change", revise).json()
            == second
        )
        assert _post(owner, "/api/v1/transfer-intents", "create-draft", body).json() == first
        assert (
            _patch(
                owner,
                f"/api/v1/transfer-intents/{intent_id}",
                "recipient-change",
                {**recipient_change, "recipient_code": "another"},
            ).status_code
            == 409
        )

        _register(foreign, "draft-foreign")
        foreign_profile = _post(
            foreign, "/api/v1/profiles", "foreign-profile", {"template_code": "regular"}
        )
        assert foreign_profile.status_code == 201
        assert foreign.get(f"/api/v1/transfer-intents/{intent_id}").status_code == 404
        assert foreign.get("/api/v1/transfer-intents").json()["items"] == []
        assert _post(foreign, "/api/v1/transfer-intents", "foreign-draft", body).status_code == 404
        assert (
            _patch(
                foreign,
                f"/api/v1/transfer-intents/{intent_id}",
                "foreign-change",
                recipient_change,
            ).status_code
            == 404
        )
        assert (
            _patch(
                owner,
                f"/api/v1/transfer-intents/{intent_id}",
                "foreign-profile-change",
                {
                    **recipient_change,
                    "expected_revision": 3,
                    "profile_id": foreign_profile.json()["profile_id"],
                },
            ).status_code
            == 404
        )
        same_account.get("/api/v1/session")
        login = _post(
            same_account,
            "/api/v1/sessions",
            "login-draft-owner",
            {"login": "draft-owner", "password": "synthetic-transfer-password"},
        )
        assert login.status_code == 201
        assert same_account.get(f"/api/v1/transfer-intents/{intent_id}").json() == third
        token = owner.cookies[SESSION_COOKIE_NAME]

    with container.engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM transfer_intents")).scalar_one() == 1
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM demo_bank_results")).scalar_one() == 0
        )
        assert (
            connection.execute(
                sa.text(
                    "SELECT COUNT(*) FROM audit_events "
                    "WHERE event_type IN ('transfer.intent.created', 'transfer.intent.revised')"
                )
            ).scalar_one()
            == 3
        )
    container.close()

    restarted = build_container(settings)
    restarted_app = create_http_app(
        readiness=restarted.readiness,
        identity_service=restarted.identity_service,
        account_service=restarted.account_service,
        financial_profiles=restarted.financial_profiles,
        transfer_intents=restarted.transfer_intents,
    )
    with TestClient(restarted_app, raise_server_exceptions=False) as resumed:
        resumed.cookies.set(SESSION_COOKIE_NAME, token)
        assert resumed.get(f"/api/v1/transfer-intents/{intent_id}").json() == third
        assert resumed.get("/api/v1/health/ready").status_code == 200
    restarted.close()
