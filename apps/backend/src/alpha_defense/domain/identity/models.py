"""Framework-free identity aggregates for the mock-only MVP."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from alpha_defense.domain.shared import EntityId

_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


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

    def is_active_at(self, now: datetime) -> bool:
        _require_utc(now, field_name="now")
        return now < self.expires_at

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
