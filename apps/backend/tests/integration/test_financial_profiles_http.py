"""P19 HTTP profiles remain synthetic, owner-scoped, and stable after restart."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from alpha_defense.application.shared import ConsentRequiredError
from alpha_defense.bootstrap import build_container, create_http_app
from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import HistoryStatus
from alpha_defense.transport.http.v1.dependencies import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def _post(client: TestClient, path: str, key: str, payload: object) -> object:
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None
    return client.post(
        path,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
        json=payload,
    )


def _register(client: TestClient, login: str) -> None:
    client.get("/api/v1/session")
    response = _post(
        client,
        "/api/v1/accounts",
        f"register-{login}",
        {"login": login, "password": "synthetic-profile-password"},
    )
    assert response.status_code == 201


def test_profile_http_owner_replay_history_consent_and_restart(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "financial-profiles.db"
    migrate(database_path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{database_path}")
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        account_service=container.account_service,
        financial_profiles=container.financial_profiles,
    )
    with (
        TestClient(app, raise_server_exceptions=False) as owner,
        TestClient(app, raise_server_exceptions=False) as foreign,
        TestClient(app, raise_server_exceptions=False) as same_account,
    ):
        assert owner.get("/api/v1/profile-templates").status_code == 401
        _register(owner, "profile-owner")
        templates = owner.get("/api/v1/profile-templates")
        assert templates.status_code == 200
        assert {item["code"] for item in templates.json()["items"]} == {
            "regular",
            "sparse",
            "empty",
        }
        assert owner.get("/api/v1/profiles").json()["items"] == []
        body = {"template_code": "regular"}
        assert owner.post("/api/v1/profiles", json=body).status_code == 403
        assert (
            owner.post(
                "/api/v1/profiles",
                headers={"X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME]},
                json=body,
            ).status_code
            == 400
        )
        created = _post(owner, "/api/v1/profiles", "create-regular", body)
        assert created.status_code == 201
        result = created.json()
        profile_id = result["profile_id"]
        assert result["execution_mode"] == "mock"
        assert result["history_version"] == 1
        assert len(result["operations"]) == 12
        assert result["template_version"] == "demo-finance-v1"
        assert _post(owner, "/api/v1/profiles", "create-regular", body).json() == result
        assert _post(owner, "/api/v1/profiles", "second-key", body).json() == result
        assert (
            _post(
                owner, "/api/v1/profiles", "create-regular", {"template_code": "sparse"}
            ).status_code
            == 409
        )
        sparse = _post(owner, "/api/v1/profiles", "create-sparse", {"template_code": "sparse"})
        assert sparse.status_code == 201
        assert len(sparse.json()["operations"]) == 5
        assert len(owner.get("/api/v1/profiles").json()["items"]) == 2
        assert owner.get(f"/api/v1/profiles/{profile_id}").json() == result

        token = owner.cookies.get(SESSION_COOKIE_NAME)
        assert token is not None
        actor = container.identity_service.resolve_actor(token)
        with pytest.raises(ConsentRequiredError, match="Разрешите использование истории"):
            container.financial_profiles.evaluate(
                actor=actor,
                profile_id=EntityId.from_string(profile_id),
                amount=Money(400_000, Currency.RUB),
                recipient_code="new-payee",
                as_of=datetime.now(UTC),
            )
        consent = owner.patch(
            "/api/v1/consents/use_transaction_history",
            headers={
                "X-CSRF-Token": owner.cookies[CSRF_COOKIE_NAME],
                "Idempotency-Key": "grant-history",
            },
            json={"status": "granted", "expected_revision": 0},
        )
        assert consent.status_code == 200
        regular = next(
            item
            for item in container.financial_profiles.list_owned(actor=actor)
            if item.template_code == "regular"
        )
        features = container.financial_profiles.evaluate(
            actor=actor,
            profile_id=regular.profile_id,
            amount=Money(400_000, Currency.RUB),
            recipient_code="new-payee",
            as_of=datetime.now(UTC),
        )
        assert features.status is HistoryStatus.COMPLETE
        assert features.sample_size == 12
        assert features.recipient_is_new and features.amount_is_outlier
        sparse_profile = next(
            item
            for item in container.financial_profiles.list_owned(actor=actor)
            if item.template_code == "sparse"
        )
        sparse_features = container.financial_profiles.evaluate(
            actor=actor,
            profile_id=sparse_profile.profile_id,
            amount=Money(400_000, Currency.RUB),
            recipient_code="new-payee",
            as_of=datetime.now(UTC),
        )
        assert sparse_features.status is HistoryStatus.INSUFFICIENT_DATA
        assert sparse_features.sample_size == 5
        assert sparse_features.amount_is_outlier is None
        empty = _post(owner, "/api/v1/profiles", "create-empty", {"template_code": "empty"})
        assert empty.status_code == 201
        assert empty.json()["operations"] == []
        empty_profile = next(
            item
            for item in container.financial_profiles.list_owned(actor=actor)
            if item.template_code == "empty"
        )
        empty_features = container.financial_profiles.evaluate(
            actor=actor,
            profile_id=empty_profile.profile_id,
            amount=Money(400_000, Currency.RUB),
            recipient_code="new-payee",
            as_of=datetime.now(UTC),
        )
        assert empty_features.status is HistoryStatus.INSUFFICIENT_DATA
        assert empty_features.sample_size == 0
        assert empty_features.recipient_is_new is None

        _register(foreign, "profile-foreign")
        assert foreign.get(f"/api/v1/profiles/{profile_id}").status_code == 404
        assert foreign.get("/api/v1/profiles").json()["items"] == []
        foreign_profile = _post(foreign, "/api/v1/profiles", "foreign-regular", body)
        assert foreign_profile.status_code == 201
        assert foreign_profile.json()["profile_id"] != profile_id

        same_account.get("/api/v1/session")
        login = _post(
            same_account,
            "/api/v1/sessions",
            "login-profile-owner",
            {"login": "profile-owner", "password": "synthetic-profile-password"},
        )
        assert login.status_code == 201
        assert same_account.get(f"/api/v1/profiles/{profile_id}").status_code == 200
        assert _post(same_account, "/api/v1/profiles", "other-session", body).json() == result

    with container.engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM financial_profiles")).scalar_one() == 4
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM completed_operations")).scalar_one()
            == 29
        )
        assert (
            connection.execute(
                sa.text("SELECT COUNT(*) FROM audit_events WHERE event_type = 'profile.created'")
            ).scalar_one()
            == 4
        )
    with pytest.raises(SQLAlchemyError), container.engine.begin() as connection:
        connection.execute(sa.text("UPDATE completed_operations SET amount_minor = 1"))
    with pytest.raises(SQLAlchemyError), container.engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM completed_operations"))
    container.close()

    restarted = build_container(settings)
    restarted_app = create_http_app(
        readiness=restarted.readiness,
        identity_service=restarted.identity_service,
        account_service=restarted.account_service,
        financial_profiles=restarted.financial_profiles,
    )
    with TestClient(restarted_app, raise_server_exceptions=False) as resumed:
        resumed.cookies.set(SESSION_COOKIE_NAME, token)
        assert resumed.get(f"/api/v1/profiles/{profile_id}").json() == result
        assert resumed.get("/api/v1/health/ready").status_code == 200
    restarted.close()
