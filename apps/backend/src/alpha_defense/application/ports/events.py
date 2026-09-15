"""Plain internal-event contracts shared by application and adapters."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeAlias, cast

from alpha_defense.domain.shared import EntityId, ExecutionMode

JsonScalar: TypeAlias = bool | int | float | str | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_TOPIC_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")


def _require_utc(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if offset.total_seconds() != 0:
        raise ValueError(f"{field_name} must be in UTC")


def _copy_json_object(value: Mapping[str, JsonValue]) -> JsonObject:
    if not isinstance(value, Mapping):
        raise TypeError("payload must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise TypeError("payload keys must be strings")
    try:
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
        decoded: object = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must contain finite JSON values") from exc
    if not isinstance(decoded, dict):
        raise TypeError("payload must be a JSON object")
    return cast(JsonObject, decoded)


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Versioned event envelope; payloads contain IDs/codes, never raw private content."""

    event_id: EntityId
    event_type: str
    aggregate_id: EntityId
    aggregate_revision: int
    occurred_at: datetime
    correlation_id: EntityId
    execution_mode: ExecutionMode
    payload: Mapping[str, JsonValue]
    causation_id: EntityId | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("event_id", "aggregate_id", "correlation_id"):
            if not isinstance(getattr(self, field_name), EntityId):
                raise TypeError(f"{field_name} must be an EntityId")
        if self.causation_id is not None and not isinstance(self.causation_id, EntityId):
            raise TypeError("causation_id must be an EntityId or None")
        if not isinstance(self.event_type, str):
            raise TypeError("event_type must be a string")
        if not _EVENT_TYPE_PATTERN.fullmatch(self.event_type):
            raise ValueError("event_type must be a namespaced stable code")
        if isinstance(self.aggregate_revision, bool) or not isinstance(
            self.aggregate_revision, int
        ):
            raise TypeError("aggregate_revision must be an integer")
        if self.aggregate_revision < 0:
            raise ValueError("aggregate_revision must be non-negative")
        if self.schema_version != 1:
            raise ValueError("only internal event schema_version=1 is supported")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        _require_utc(self.occurred_at, field_name="occurred_at")
        object.__setattr__(self, "payload", _copy_json_object(self.payload))


@dataclass(frozen=True, slots=True)
class AuditReceipt:
    event_id: EntityId
    recorded_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.recorded_at, field_name="recorded_at")


@dataclass(frozen=True, slots=True)
class OutboxReceipt:
    message_id: EntityId
    accepted_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.accepted_at, field_name="accepted_at")


class AuditPort(Protocol):
    """Append immutable audit data inside the caller's local transaction."""

    def append(
        self,
        event: EventEnvelope,
        *,
        actor_id: EntityId | None,
        session_id: EntityId | None,
        namespace_id: EntityId | None,
    ) -> AuditReceipt: ...


class EventSinkPort(Protocol):
    """Queue an event inside the caller's local transaction."""

    def append(self, event: EventEnvelope, *, topic: str) -> OutboxReceipt: ...


EventHandler: TypeAlias = Callable[[EventEnvelope], None]


def validate_topic(topic: str) -> None:
    if not isinstance(topic, str):
        raise TypeError("topic must be a string")
    if not _TOPIC_PATTERN.fullmatch(topic):
        raise ValueError("topic must be a stable lowercase code")
