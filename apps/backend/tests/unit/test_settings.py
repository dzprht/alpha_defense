"""Configuration and prepared command-guard tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError

from alpha_defense.bootstrap import ConfigurationError, Settings, build_container
from alpha_defense.transport.http.v1.errors import install_exception_handlers
from alpha_defense.transport.http.v1.guards import require_csrf, require_idempotency_key


def settings_values(tmp_path: Path, **overrides: object) -> dict[str, object]:
    content_root = tmp_path / "content"
    fixture_root = tmp_path / "fixtures"
    media_root = tmp_path / "media"
    for path in (content_root, fixture_root, media_root):
        path.mkdir(exist_ok=True)
    values: dict[str, object] = {
        "app_env": "test",
        "execution_mode": "mock",
        "database_url": f"sqlite:///{tmp_path / 'app.db'}",
        "content_root": content_root,
        "fixture_root": fixture_root,
        "media_root": media_root,
        "session_secret": "test-session-secret-with-32-characters",
        "policy_version": "demo-risk-v1",
        "trusted_support_contact": "900",
    }
    values.update(overrides)
    return values


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings.model_validate(settings_values(tmp_path, **overrides))


def test_settings_load_architecture_environment_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for name, value in settings_values(tmp_path).items():
        monkeypatch.setenv(name.upper(), str(value))

    settings = Settings()

    assert settings.app_env.value == "test"
    assert settings.execution_mode.value == "mock"
    assert settings.policy_file.name == "demo-risk-v1.json"
    assert settings.cors_origins == ("http://localhost:5173",)


@pytest.mark.parametrize(
    ("overrides", "expected_fragment"),
    [
        ({"execution_mode": "unsupported"}, "execution_mode"),
        ({"session_secret": "short"}, "32 characters"),
        (
            {"app_env": "local", "session_secret": "replace-with-a-long-placeholder-secret"},
            "placeholder",
        ),
        ({"cors_allow_origins": "*"}, "explicit"),
    ],
)
def test_invalid_settings_fail_without_echoing_secret(
    tmp_path: Path,
    overrides: dict[str, object],
    expected_fragment: str,
) -> None:
    with pytest.raises(PydanticValidationError) as captured:
        make_settings(tmp_path, **overrides)

    rendered = str(captured.value)
    assert expected_fragment in rendered
    assert "replace-with-a-long-placeholder-secret" not in rendered


def test_container_rejects_live_mode_before_connecting(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, execution_mode="live")

    with pytest.raises(ConfigurationError, match="no verified adapters"):
        build_container(settings)


def test_container_rejects_missing_database_without_creating_it(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    database_path = tmp_path / "app.db"

    with pytest.raises(ConfigurationError, match="existing migrated database"):
        build_container(settings)

    assert not database_path.exists()


def test_prepared_command_guards_accept_only_matching_csrf_and_clean_key() -> None:
    app = FastAPI()
    install_exception_handlers(app)

    @app.post("/guarded")
    async def guarded(request: Request) -> dict[str, str]:
        require_csrf(request)
        return {"key": require_idempotency_key(request)}

    client = TestClient(app)
    client.cookies.set("alpha_defense_csrf", "same-token")
    accepted = client.post(
        "/guarded",
        headers={"X-CSRF-Token": "same-token", "Idempotency-Key": "command-1"},
    )
    client.cookies.set("alpha_defense_csrf", "one-token")
    rejected = client.post(
        "/guarded",
        headers={"X-CSRF-Token": "another-token", "Idempotency-Key": "command-1"},
    )

    assert accepted.status_code == 200
    assert accepted.json() == {"key": "command-1"}
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "csrf_failed"
