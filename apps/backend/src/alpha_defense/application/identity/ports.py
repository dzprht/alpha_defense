"""Ports required by identity application use cases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from alpha_defense.application.identity.dto import (
    ConsentView,
    SessionBootstrapResult,
    StartSessionResult,
)
from alpha_defense.application.ports import JsonValue, UnitOfWorkPort
from alpha_defense.application.shared import ActorContext
from alpha_defense.domain.identity import (
    ConsentScope,
    ConsentSnapshot,
    ConsentStatus,
    DemoSession,
    PreSession,
    SessionRole,
    SyntheticUser,
)
from alpha_defense.domain.shared import EntityId


@dataclass(frozen=True, slots=True)
class AuthenticatedDemoSubject:
    profile_code: str
    roles: frozenset[SessionRole]


class DemoIdentityProviderPort(Protocol):
    def authenticate(self, profile_code: str) -> AuthenticatedDemoSubject | None: ...


class SecurityTokenPort(Protocol):
    def new_pre_session_token(self) -> str: ...

    def fingerprint(self, token: str) -> str: ...

    def fingerprint_principal(self, parts: Sequence[str]) -> str: ...

    def fingerprint_command(self, command: Mapping[str, JsonValue]) -> str: ...

    def derive_session_token(self, pre_session_token: str, session_id: EntityId) -> str: ...

    def derive_csrf_token(self, bearer_token: str) -> str: ...


class IdentityRepositoryPort(Protocol):
    def add_user(self, user: SyntheticUser) -> None: ...

    def get_user(self, user_id: EntityId) -> SyntheticUser | None: ...

    def add_pre_session(self, pre_session: PreSession) -> None: ...

    def get_pre_session_by_fingerprint(self, token_fingerprint: str) -> PreSession | None: ...

    def save_pre_session(
        self,
        pre_session: PreSession,
        *,
        expected_consumed_session_id: EntityId | None,
    ) -> None: ...

    def add_session(self, session: DemoSession) -> None: ...

    def get_session(self, session_id: EntityId) -> DemoSession | None: ...

    def get_session_by_fingerprint(self, token_fingerprint: str) -> DemoSession | None: ...

    def save_session(self, session: DemoSession, *, expected_consent_revision: int) -> None: ...

    def add_consent(self, consent: ConsentSnapshot) -> None: ...

    def get_consent(self, user_id: EntityId, scope: ConsentScope) -> ConsentSnapshot | None: ...

    def list_consents(self, user_id: EntityId) -> tuple[ConsentSnapshot, ...]: ...

    def save_consent(self, consent: ConsentSnapshot, *, expected_revision: int) -> None: ...


class IdentityUnitOfWorkPort(UnitOfWorkPort, Protocol):
    @property
    def identity(self) -> IdentityRepositoryPort: ...


class IdentityUnitOfWorkFactory(Protocol):
    def __call__(self) -> IdentityUnitOfWorkPort: ...


class IdentityServicePort(Protocol):
    def bootstrap_session(
        self,
        *,
        session_token: str | None,
        pre_session_token: str | None,
    ) -> SessionBootstrapResult: ...

    def start_session(
        self,
        *,
        pre_session_token: str,
        idempotency_key: str,
        profile_code: str,
    ) -> StartSessionResult: ...

    def resolve_actor(self, session_token: str) -> ActorContext: ...

    def update_consent(
        self,
        *,
        actor: ActorContext,
        idempotency_key: str,
        scope: ConsentScope,
        status: ConsentStatus,
        expected_revision: int,
    ) -> ConsentView: ...
