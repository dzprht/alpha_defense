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
    Account,
    ConsentScope,
    ConsentSnapshot,
    ConsentStatus,
    DemoSession,
    LoginThrottle,
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

    def fingerprint_credentials(self, login: str, password: str) -> str: ...

    def fingerprint_login(self, login: str) -> str: ...


class CredentialPort(Protocol):
    def hash_password(self, password: str) -> str: ...

    def verify_password(self, password_hash: str | None, password: str) -> bool: ...


class AccountRepositoryPort(Protocol):
    def add(self, account: Account) -> None: ...

    def get_by_id(self, user_id: EntityId) -> Account | None: ...

    def get_by_login(self, normalized_login: str) -> Account | None: ...

    def save_consent_revision(self, account: Account, *, expected_revision: int) -> None: ...

    def get_throttle(self, login_fingerprint: str) -> LoginThrottle | None: ...

    def add_throttle(self, throttle: LoginThrottle) -> None: ...

    def save_throttle(self, throttle: LoginThrottle, *, expected_revision: int) -> None: ...


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

    def revoke_session(self, session: DemoSession) -> None: ...

    def add_consent(self, consent: ConsentSnapshot) -> None: ...

    def get_consent(self, user_id: EntityId, scope: ConsentScope) -> ConsentSnapshot | None: ...

    def list_consents(self, user_id: EntityId) -> tuple[ConsentSnapshot, ...]: ...

    def save_consent(self, consent: ConsentSnapshot, *, expected_revision: int) -> None: ...


class IdentityUnitOfWorkPort(UnitOfWorkPort, Protocol):
    @property
    def identity(self) -> IdentityRepositoryPort: ...

    @property
    def accounts(self) -> AccountRepositoryPort: ...


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


class AccountServicePort(Protocol):
    def register(
        self,
        *,
        pre_session_token: str,
        idempotency_key: str,
        login: str,
        password: str,
    ) -> StartSessionResult: ...

    def login(
        self,
        *,
        pre_session_token: str,
        idempotency_key: str,
        login: str,
        password: str,
    ) -> StartSessionResult: ...

    def logout(self, *, session_token: str, idempotency_key: str) -> None: ...
