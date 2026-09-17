"""Validated process configuration loaded only by the composition root."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from alpha_defense.domain.shared import ExecutionMode


class AppEnvironment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Fail-fast settings with no implicit local secret or storage defaults."""

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    app_env: AppEnvironment
    execution_mode: ExecutionMode
    database_url: str = Field(min_length=1)
    content_root: Path
    fixture_root: Path
    media_root: Path
    session_secret: SecretStr
    policy_version: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    analysis_deadline_ms: int = Field(default=3000, ge=100, le=30_000)
    call_proof_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    transfer_check_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    correlation_window_seconds: int = Field(default=3600, ge=1, le=86_400)
    research_enabled: bool = False
    trusted_support_contact: str = Field(min_length=1, max_length=128)
    cors_allow_origins: str = "http://localhost:5173"
    trusted_hosts: str = "127.0.0.1,localhost,testserver"
    max_request_body_bytes: int = Field(default=1_048_576, ge=1024, le=20_971_520)

    @field_validator("database_url", "trusted_support_contact")
    @classmethod
    def _must_be_trimmed(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("must be trimmed")
        return value

    @model_validator(mode="after")
    def _validate_security_boundaries(self) -> Self:
        secret = self.session_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        if self.app_env is not AppEnvironment.TEST and any(
            marker in secret.lower() for marker in ("replace", "change-me", "placeholder")
        ):
            raise ValueError("SESSION_SECRET must not be a placeholder")
        if not self.cors_origins:
            raise ValueError("CORS_ALLOW_ORIGINS must not be empty")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ALLOW_ORIGINS must be explicit")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            raise ValueError("TRUSTED_HOSTS must be an explicit non-empty list")
        return self

    @property
    def cors_origins(self) -> tuple[str, ...]:
        return _split_csv(self.cors_allow_origins)

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return _split_csv(self.trusted_hosts)

    @property
    def policy_file(self) -> Path:
        return self.content_root / "policies" / f"{self.policy_version}.json"


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())
