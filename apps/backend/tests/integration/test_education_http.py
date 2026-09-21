"""Authenticated HTTP scenarios for the published education catalog."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alpha_defense.bootstrap import build_container, create_http_app
from alpha_defense.transport.http.v1.dependencies import CSRF_COOKIE_NAME
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


@pytest.fixture
def education_client(tmp_path: Path) -> Iterator[TestClient]:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "education-http.db"
    migrate(database_path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{database_path}")
    container = build_container(settings)
    app = create_http_app(
        readiness=container.readiness,
        identity_service=container.identity_service,
        list_cards=container.list_cards,
        get_card=container.get_card,
        cors_origins=settings.cors_origins,
        allowed_hosts=settings.allowed_hosts,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    container.close()


def _start_session(client: TestClient) -> None:
    anonymous = client.get("/api/v1/session")
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert anonymous.status_code == 200
    assert csrf is not None
    created = client.post(
        "/api/v1/sessions/demo",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "education-session"},
        json={"profile_code": "demo-user"},
    )
    assert created.status_code == 201


def test_education_api_requires_session_and_paginates(education_client: TestClient) -> None:
    anonymous = education_client.get("/api/v1/education/cards")
    _start_session(education_client)
    first = education_client.get("/api/v1/education/cards", params={"limit": 2})
    cursor = first.json()["next_cursor"]
    second = education_client.get(
        "/api/v1/education/cards",
        params={"limit": 100, "cursor": cursor},
    )

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "session_required"
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 5
    assert second.json()["next_cursor"] is None


def test_education_api_returns_explicit_locale_and_card_fallback(
    education_client: TestClient,
) -> None:
    _start_session(education_client)
    localized = education_client.get(
        "/api/v1/education/cards/general_safety",
        params={"locale": "en-US"},
    )
    unknown = education_client.get("/api/v1/education/cards/future_card")
    old = education_client.get(
        "/api/v1/education/cards/general_safety",
        params={"version": "9.9.9"},
    )
    malformed = education_client.get(
        "/api/v1/education/cards",
        params={"locale": "english"},
    )

    assert localized.status_code == 200
    assert localized.json()["locale"] == "ru-RU"
    assert localized.json()["locale_fallback"] is True
    assert unknown.status_code == 200
    assert unknown.json()["code"] == "general_safety"
    assert unknown.json()["fallback_reason"] == "unsupported_code"
    assert old.json()["fallback_reason"] == "unsupported_version"
    assert malformed.status_code == 422
    assert malformed.json()["code"] == "validation_failed"
