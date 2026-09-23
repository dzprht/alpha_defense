"""Public session and consent schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha_defense.application.identity import (
    AnonymousSessionView,
    ConsentScope,
    ConsentStatus,
    ConsentView,
    SessionView,
)


class StartDemoSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_code: str = Field(min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")


class AccountCredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=128)


class UpdateConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ConsentStatus
    expected_revision: int = Field(ge=0)


class ConsentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: ConsentScope
    status: ConsentStatus
    revision: int = Field(ge=0)
    changed_at: datetime

    @classmethod
    def from_view(cls, view: ConsentView) -> ConsentResponse:
        return cls(
            scope=view.scope,
            status=view.status,
            revision=view.revision,
            changed_at=view.changed_at,
        )


class AnonymousSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["anonymous"] = "anonymous"
    pre_session_expires_at: datetime
    execution_mode: Literal["mock"] = "mock"
    capabilities: tuple[Literal["start_demo_session"], ...]

    @classmethod
    def from_view(cls, view: AnonymousSessionView) -> AnonymousSessionResponse:
        return cls(
            pre_session_expires_at=view.pre_session_expires_at,
            capabilities=("start_demo_session",),
        )


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active"] = "active"
    user_id: str
    session_id: str
    namespace_id: str
    auth_kind: Literal["demo", "account"]
    roles: tuple[Literal["demo_user", "researcher"], ...]
    consent_revision: int = Field(ge=0)
    consents: tuple[ConsentResponse, ...]
    execution_mode: Literal["mock"] = "mock"
    expires_at: datetime
    capabilities: tuple[Literal["update_consents"], ...]

    @classmethod
    def from_view(cls, view: SessionView) -> SessionResponse:
        return cls(
            user_id=str(view.user_id),
            session_id=str(view.session_id),
            namespace_id=str(view.namespace_id),
            auth_kind=view.auth_kind.value,
            roles=tuple(role.value for role in view.roles),
            consent_revision=view.consent_revision,
            consents=tuple(ConsentResponse.from_view(item) for item in view.consents),
            expires_at=view.expires_at,
            capabilities=("update_consents",),
        )
