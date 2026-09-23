"""Framework-free identity aggregates for the mock-only MVP."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from alpha_defense.domain.shared import EntityId

_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_LOGIN_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{2,63}$")


class ConsentScope(StrEnum):
    ANALYZE_COMMUNICATIONS = "analyze_communications"
    ANALYZE_RESOURCES = "analyze_resources"
    USE_TRANSACTION_HISTORY = "use_transaction_history"
    SEND_NOTIFICATIONS = "send_notifications"
    PARTICIPATE_IN_RESEARCH = "participate_in_research"


class ConsentStatus(StrEnum):
    GRANTED = "granted"
    REVOKED = "revoked"


class SessionRole(StrEnum):
    DEMO_USER = "demo_user"
    RESEARCHER = "researcher"


class SessionAuthKind(StrEnum):
    DEMO = "demo"
    ACCOUNT = "account"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


def normalize_login(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("login must be a string")
    normalized = value.strip().casefold()
    if not _LOGIN_PATTERN.fullmatch(normalized):
        raise ValueError("login must contain 3..64 ASCII letters, digits, dots or separators")
    return normalized


def _require_utc(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC-aware")


def _require_digest(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _DIGEST_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class SyntheticUser:
    user_id: EntityId
    profile_code: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, EntityId):
            raise TypeError("user_id must be an EntityId")
        if not isinstance(self.profile_code, str) or not _PROFILE_CODE_PATTERN.fullmatch(
            self.profile_code
        ):
            raise ValueError("profile_code must use the synthetic profile code format")
        _require_utc(self.created_at, field_name="created_at")


@dataclass(frozen=True, slots=True)
class Account:
    user_id: EntityId
    normalized_login: str
    password_hash: str
    namespace_id: EntityId
    status: AccountStatus
    consent_revision: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, EntityId) or not isinstance(self.namespace_id, EntityId):
            raise TypeError("account IDs must be EntityId values")
        if self.normalized_login != normalize_login(self.normalized_login):
            raise ValueError("login must be normalized")
        if (
            not isinstance(self.password_hash, str)
            or not self.password_hash
            or len(self.password_hash) > 512
        ):
            raise ValueError("password hash must be non-empty and bounded")
        if not isinstance(self.status, AccountStatus):
            raise TypeError("status must be AccountStatus")
        if type(self.consent_revision) is not int or self.consent_revision < 0:
            raise ValueError("consent revision must be non-negative")
        _require_utc(self.created_at, field_name="created_at")

    def advance_consent_revision(self, *, expected_revision: int) -> Account:
        if self.consent_revision != expected_revision:
            raise ValueError("account consent revision is stale")
        return replace(self, consent_revision=self.consent_revision + 1)


@dataclass(frozen=True, slots=True)
class LoginThrottle:
    login_fingerprint: str
    failures: int
    window_started_at: datetime
    blocked_until: datetime | None
    revision: int

    def __post_init__(self) -> None:
        _require_digest(self.login_fingerprint, field_name="login_fingerprint")
        if type(self.failures) is not int or self.failures < 0:
            raise ValueError("failures must be non-negative")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("revision must be non-negative")
        _require_utc(self.window_started_at, field_name="window_started_at")
        if self.blocked_until is not None:
            _require_utc(self.blocked_until, field_name="blocked_until")

    def is_blocked_at(self, now: datetime) -> bool:
        _require_utc(now, field_name="now")
        return self.blocked_until is not None and now < self.blocked_until


@dataclass(frozen=True, slots=True)
class PreSession:
    pre_session_id: EntityId
    token_fingerprint: str
    created_at: datetime
    expires_at: datetime
    consumed_session_id: EntityId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pre_session_id, EntityId):
            raise TypeError("pre_session_id must be an EntityId")
        _require_digest(self.token_fingerprint, field_name="token_fingerprint")
        _require_utc(self.created_at, field_name="created_at")
        _require_utc(self.expires_at, field_name="expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        if self.consumed_session_id is not None and not isinstance(
            self.consumed_session_id, EntityId
        ):
            raise TypeError("consumed_session_id must be an EntityId or None")

    def is_available_at(self, now: datetime) -> bool:
        _require_utc(now, field_name="now")
        return self.consumed_session_id is None and now < self.expires_at

    def consume(self, session_id: EntityId, *, now: datetime) -> PreSession:
        if not self.is_available_at(now):
            raise ValueError("pre-session is expired or already consumed")
        return replace(self, consumed_session_id=session_id)


@dataclass(frozen=True, slots=True)
class DemoSession:
    session_id: EntityId
    user_id: EntityId
    manual_namespace_id: EntityId
    roles: frozenset[SessionRole]
    token_fingerprint: str
    consent_revision: int
    created_at: datetime
    expires_at: datetime
    auth_kind: SessionAuthKind = SessionAuthKind.DEMO
    workspace_namespace_id: EntityId | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("session_id", "user_id", "manual_namespace_id"):
            if not isinstance(getattr(self, field_name), EntityId):
                raise TypeError(f"{field_name} must be an EntityId")
        if not isinstance(self.roles, frozenset) or not self.roles:
            raise ValueError("roles must be a non-empty frozenset")
        if any(not isinstance(role, SessionRole) for role in self.roles):
            raise TypeError("roles must contain SessionRole values")
        _require_digest(self.token_fingerprint, field_name="token_fingerprint")
        if isinstance(self.consent_revision, bool) or not isinstance(self.consent_revision, int):
            raise TypeError("consent_revision must be an integer")
        if self.consent_revision < 0:
            raise ValueError("consent_revision must be non-negative")
        _require_utc(self.created_at, field_name="created_at")
        _require_utc(self.expires_at, field_name="expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
        if not isinstance(self.auth_kind, SessionAuthKind):
            raise TypeError("auth_kind must be SessionAuthKind")
        if self.workspace_namespace_id is not None and not isinstance(
            self.workspace_namespace_id, EntityId
        ):
            raise TypeError("workspace_namespace_id must be EntityId or None")
        if self.auth_kind is SessionAuthKind.ACCOUNT and self.workspace_namespace_id is None:
            raise ValueError("account sessions require a workspace namespace")
        if self.revoked_at is not None:
            _require_utc(self.revoked_at, field_name="revoked_at")
            if self.revoked_at < self.created_at:
                raise ValueError("revoked_at cannot precede creation")

    @property
    def namespace_id(self) -> EntityId:
        return self.workspace_namespace_id or self.manual_namespace_id

    def is_active_at(self, now: datetime) -> bool:
        _require_utc(now, field_name="now")
        return self.revoked_at is None and now < self.expires_at

    def revoke(self, *, at: datetime) -> DemoSession:
        if self.revoked_at is not None:
            return self
        return replace(self, revoked_at=at)

    def advance_consent_revision(self, *, expected_revision: int) -> DemoSession:
        if expected_revision != self.consent_revision:
            raise ValueError("session consent revision is stale")
        return replace(self, consent_revision=self.consent_revision + 1)


@dataclass(frozen=True, slots=True)
class ConsentSnapshot:
    user_id: EntityId
    scope: ConsentScope
    status: ConsentStatus
    revision: int
    changed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, EntityId):
            raise TypeError("user_id must be an EntityId")
        if not isinstance(self.scope, ConsentScope):
            raise TypeError("scope must be a ConsentScope")
        if not isinstance(self.status, ConsentStatus):
            raise TypeError("status must be a ConsentStatus")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise TypeError("revision must be an integer")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        _require_utc(self.changed_at, field_name="changed_at")

    def change(
        self,
        status: ConsentStatus,
        *,
        revision: int,
        changed_at: datetime,
    ) -> ConsentSnapshot:
        if not isinstance(status, ConsentStatus):
            raise TypeError("status must be a ConsentStatus")
        if revision <= self.revision:
            raise ValueError("consent revision must advance")
        return replace(self, status=status, revision=revision, changed_at=changed_at)
