"""Repository contracts and technical persistence records."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol, TypeVar

from alpha_defense.application.ports.events import (
    EventEnvelope,
    JsonValue,
    _copy_json_object,
    _require_utc,
    validate_topic,
)
from alpha_defense.domain.shared import EntityId

_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")


def _require_trimmed(value: str, *, field_name: str, max_length: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip() or len(value) > max_length:
        raise ValueError(f"{field_name} must be trimmed and contain 1..{max_length} characters")


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    """Server-derived command namespace; principal is a digest, never a bearer token."""

    principal_fingerprint: str
    method: str
    canonical_route: str
    key: str
    session_id: EntityId | None = None
    namespace_id: EntityId | None = None

    def __post_init__(self) -> None:
        if not _DIGEST_PATTERN.fullmatch(self.principal_fingerprint):
            raise ValueError("principal_fingerprint must be a lowercase SHA-256 digest")
        if self.method not in {"POST", "PATCH"}:
            raise ValueError("method must be POST or PATCH")
        _require_trimmed(self.canonical_route, field_name="canonical_route", max_length=255)
        if not self.canonical_route.startswith("/"):
            raise ValueError("canonical_route must start with '/'")
        _require_trimmed(self.key, field_name="key", max_length=255)
        for field_name in ("session_id", "namespace_id"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, EntityId):
                raise TypeError(f"{field_name} must be an EntityId or None")


class IdempotencyState(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    record_id: EntityId
    scope: IdempotencyScope
    command_hash: str
    resource_id: EntityId
    state: IdempotencyState
    result: Mapping[str, JsonValue] | None
    revision: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not _DIGEST_PATTERN.fullmatch(self.command_hash):
            raise ValueError("command_hash must be a lowercase SHA-256 digest")
        if not isinstance(self.state, IdempotencyState):
            raise TypeError("state must be an IdempotencyState")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise TypeError("revision must be an integer")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        _require_utc(self.created_at, field_name="created_at")
        _require_utc(self.updated_at, field_name="updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.result is not None:
            object.__setattr__(self, "result", _copy_json_object(self.result))
        if self.state is IdempotencyState.IN_PROGRESS and self.result is not None:
            raise ValueError("in-progress idempotency records cannot have a result")
        if self.state is not IdempotencyState.IN_PROGRESS and self.result is None:
            raise ValueError("finished idempotency records require a result")

    def finish(
        self,
        *,
        state: IdempotencyState,
        result: Mapping[str, JsonValue],
        updated_at: datetime,
    ) -> IdempotencyRecord:
        if state is IdempotencyState.IN_PROGRESS:
            raise ValueError("finish state must be completed or failed")
        return replace(
            self,
            state=state,
            result=_copy_json_object(result),
            revision=self.revision + 1,
            updated_at=updated_at,
        )


@dataclass(frozen=True, slots=True)
class IdempotencyReservation:
    record: IdempotencyRecord
    is_new: bool


@dataclass(frozen=True, slots=True)
class AuditRecord:
    event: EventEnvelope
    recorded_at: datetime
    actor_id: EntityId | None = None
    session_id: EntityId | None = None
    namespace_id: EntityId | None = None

    def __post_init__(self) -> None:
        _require_utc(self.recorded_at, field_name="recorded_at")
        for field_name in ("actor_id", "session_id", "namespace_id"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, EntityId):
                raise TypeError(f"{field_name} must be an EntityId or None")


class OutboxState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    message_id: EntityId
    event: EventEnvelope
    topic: str
    state: OutboxState
    attempts: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    delivered_at: datetime | None
    last_error_code: str | None
    revision: int
    created_at: datetime

    def __post_init__(self) -> None:
        validate_topic(self.topic)
        if not isinstance(self.state, OutboxState):
            raise TypeError("state must be an OutboxState")
        for field_name in ("attempts", "revision"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        for field_name in ("next_attempt_at", "created_at"):
            _require_utc(getattr(self, field_name), field_name=field_name)
        for field_name in ("lease_expires_at", "delivered_at"):
            value = getattr(self, field_name)
            if value is not None:
                _require_utc(value, field_name=field_name)
                if value < self.created_at:
                    raise ValueError(f"{field_name} must not precede created_at")
        if self.next_attempt_at < self.created_at:
            raise ValueError("next_attempt_at must not precede created_at")
        if self.state is OutboxState.PENDING and self.lease_expires_at is not None:
            raise ValueError("pending outbox messages cannot have a lease")
        if self.state is OutboxState.PROCESSING and self.lease_expires_at is None:
            raise ValueError("processing outbox messages require a lease")
        if self.state is OutboxState.DELIVERED:
            if self.delivered_at is None or self.lease_expires_at is not None:
                raise ValueError("delivered messages require delivered_at and no lease")
        elif self.delivered_at is not None:
            raise ValueError("only delivered messages can have delivered_at")
        if self.state is not OutboxState.PENDING and self.last_error_code is not None:
            raise ValueError("only pending messages can have a last error")
        if self.last_error_code is not None and not _ERROR_CODE_PATTERN.fullmatch(
            self.last_error_code
        ):
            raise ValueError("last_error_code must be a stable lowercase code")


RepositoryItem = TypeVar("RepositoryItem")


class RepositoryPort(Protocol[RepositoryItem]):
    def get(self, entity_id: EntityId) -> RepositoryItem | None: ...

    def add(self, entity: RepositoryItem) -> None: ...

    def save(self, entity: RepositoryItem, *, expected_revision: int) -> None: ...


class IdempotencyRepositoryPort(Protocol):
    def get(self, scope: IdempotencyScope) -> IdempotencyRecord | None: ...

    def get_by_id(self, record_id: EntityId) -> IdempotencyRecord | None: ...

    def reserve(self, record: IdempotencyRecord) -> IdempotencyReservation: ...

    def save(self, record: IdempotencyRecord, *, expected_revision: int) -> None: ...


class AuditRepositoryPort(Protocol):
    def append(self, record: AuditRecord) -> None: ...

    def get(self, event_id: EntityId) -> AuditRecord | None: ...

    def list_all(self) -> Sequence[AuditRecord]: ...


class OutboxRepositoryPort(Protocol):
    def add(self, message: OutboxMessage) -> None: ...

    def get(self, message_id: EntityId) -> OutboxMessage | None: ...

    def list_all(self) -> Sequence[OutboxMessage]: ...

    def claim_next(self, *, now: datetime, lease_expires_at: datetime) -> OutboxMessage | None: ...

    def mark_delivered(
        self, message_id: EntityId, *, expected_revision: int, delivered_at: datetime
    ) -> OutboxMessage: ...

    def reschedule(
        self,
        message_id: EntityId,
        *,
        expected_revision: int,
        next_attempt_at: datetime,
        error_code: str,
    ) -> OutboxMessage: ...
