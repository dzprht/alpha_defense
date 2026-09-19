"""Explicit row mappings; ORM rows never cross the infrastructure boundary."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.engine import RowMapping

from alpha_defense.application.ports import (
    AuditRecord,
    EventEnvelope,
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    OutboxMessage,
    OutboxState,
)
from alpha_defense.application.ports.events import JsonObject
from alpha_defense.domain.identity import (
    ConsentScope,
    ConsentSnapshot,
    ConsentStatus,
    DemoSession,
    PreSession,
    SessionRole,
    SyntheticUser,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode


def dump_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def load_json_object(value: str) -> JsonObject:
    decoded: object = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("persisted JSON value must be an object")
    return cast(JsonObject, decoded)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def optional_id(value: str | None) -> EntityId | None:
    return None if value in {None, ""} else EntityId.from_string(value)


def user_values(user: SyntheticUser) -> dict[str, Any]:
    return {
        "user_id": str(user.user_id),
        "profile_code": user.profile_code,
        "created_at": user.created_at,
    }


def user_from_row(row: RowMapping) -> SyntheticUser:
    return SyntheticUser(
        user_id=EntityId.from_string(row["user_id"]),
        profile_code=row["profile_code"],
        created_at=as_utc(row["created_at"]),
    )


def pre_session_values(pre_session: PreSession) -> dict[str, Any]:
    return {
        "pre_session_id": str(pre_session.pre_session_id),
        "token_fingerprint": pre_session.token_fingerprint,
        "created_at": pre_session.created_at,
        "expires_at": pre_session.expires_at,
        "consumed_session_id": (
            None
            if pre_session.consumed_session_id is None
            else str(pre_session.consumed_session_id)
        ),
    }


def pre_session_from_row(row: RowMapping) -> PreSession:
    return PreSession(
        pre_session_id=EntityId.from_string(row["pre_session_id"]),
        token_fingerprint=row["token_fingerprint"],
        created_at=as_utc(row["created_at"]),
        expires_at=as_utc(row["expires_at"]),
        consumed_session_id=optional_id(row["consumed_session_id"]),
    )


def session_values(session: DemoSession) -> dict[str, Any]:
    return {
        "session_id": str(session.session_id),
        "user_id": str(session.user_id),
        "manual_namespace_id": str(session.manual_namespace_id),
        "roles_json": dump_json([role.value for role in sorted(session.roles, key=str)]),
        "token_fingerprint": session.token_fingerprint,
        "consent_revision": session.consent_revision,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
    }


def session_from_row(row: RowMapping) -> DemoSession:
    decoded: object = json.loads(row["roles_json"])
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError("persisted session roles must be a string list")
    return DemoSession(
        session_id=EntityId.from_string(row["session_id"]),
        user_id=EntityId.from_string(row["user_id"]),
        manual_namespace_id=EntityId.from_string(row["manual_namespace_id"]),
        roles=frozenset(SessionRole(item) for item in decoded),
        token_fingerprint=row["token_fingerprint"],
        consent_revision=row["consent_revision"],
        created_at=as_utc(row["created_at"]),
        expires_at=as_utc(row["expires_at"]),
    )


def consent_values(consent: ConsentSnapshot) -> dict[str, Any]:
    return {
        "user_id": str(consent.user_id),
        "scope": consent.scope.value,
        "status": consent.status.value,
        "revision": consent.revision,
        "changed_at": consent.changed_at,
    }


def consent_from_row(row: RowMapping) -> ConsentSnapshot:
    return ConsentSnapshot(
        user_id=EntityId.from_string(row["user_id"]),
        scope=ConsentScope(row["scope"]),
        status=ConsentStatus(row["status"]),
        revision=row["revision"],
        changed_at=as_utc(row["changed_at"]),
    )


def event_values(event: EventEnvelope) -> dict[str, Any]:
    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "aggregate_id": str(event.aggregate_id),
        "aggregate_revision": event.aggregate_revision,
        "occurred_at": event.occurred_at,
        "correlation_id": str(event.correlation_id),
        "causation_id": None if event.causation_id is None else str(event.causation_id),
        "execution_mode": event.execution_mode.value,
        "payload_json": dump_json(event.payload),
    }


def event_from_row(row: RowMapping) -> EventEnvelope:
    return EventEnvelope(
        event_id=EntityId.from_string(row["event_id"]),
        event_type=row["event_type"],
        schema_version=row["schema_version"],
        aggregate_id=EntityId.from_string(row["aggregate_id"]),
        aggregate_revision=row["aggregate_revision"],
        occurred_at=as_utc(row["occurred_at"]),
        correlation_id=EntityId.from_string(row["correlation_id"]),
        causation_id=optional_id(row["causation_id"]),
        execution_mode=ExecutionMode(row["execution_mode"]),
        payload=load_json_object(row["payload_json"]),
    )


def idempotency_values(record: IdempotencyRecord) -> dict[str, Any]:
    return {
        "record_id": str(record.record_id),
        "principal_fingerprint": record.scope.principal_fingerprint,
        "session_id": "" if record.scope.session_id is None else str(record.scope.session_id),
        "namespace_id": "" if record.scope.namespace_id is None else str(record.scope.namespace_id),
        "method": record.scope.method,
        "canonical_route": record.scope.canonical_route,
        "idempotency_key": record.scope.key,
        "command_hash": record.command_hash,
        "resource_id": str(record.resource_id),
        "state": record.state.value,
        "result_json": None if record.result is None else dump_json(record.result),
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def idempotency_from_row(row: RowMapping) -> IdempotencyRecord:
    result_json = row["result_json"]
    return IdempotencyRecord(
        record_id=EntityId.from_string(row["record_id"]),
        scope=IdempotencyScope(
            principal_fingerprint=row["principal_fingerprint"],
            session_id=optional_id(row["session_id"]),
            namespace_id=optional_id(row["namespace_id"]),
            method=row["method"],
            canonical_route=row["canonical_route"],
            key=row["idempotency_key"],
        ),
        command_hash=row["command_hash"],
        resource_id=EntityId.from_string(row["resource_id"]),
        state=IdempotencyState(row["state"]),
        result=None if result_json is None else load_json_object(result_json),
        revision=row["revision"],
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )


def audit_values(record: AuditRecord) -> dict[str, Any]:
    values = event_values(record.event)
    values.update(
        actor_id=None if record.actor_id is None else str(record.actor_id),
        session_id=None if record.session_id is None else str(record.session_id),
        namespace_id=None if record.namespace_id is None else str(record.namespace_id),
        recorded_at=record.recorded_at,
    )
    return values


def audit_from_row(row: RowMapping) -> AuditRecord:
    return AuditRecord(
        event=event_from_row(row),
        actor_id=optional_id(row["actor_id"]),
        session_id=optional_id(row["session_id"]),
        namespace_id=optional_id(row["namespace_id"]),
        recorded_at=as_utc(row["recorded_at"]),
    )


def outbox_values(message: OutboxMessage) -> dict[str, Any]:
    values = event_values(message.event)
    values.update(
        message_id=str(message.message_id),
        topic=message.topic,
        state=message.state.value,
        attempts=message.attempts,
        next_attempt_at=message.next_attempt_at,
        lease_expires_at=message.lease_expires_at,
        delivered_at=message.delivered_at,
        last_error_code=message.last_error_code,
        revision=message.revision,
        created_at=message.created_at,
    )
    return values


def outbox_from_row(row: RowMapping) -> OutboxMessage:
    return OutboxMessage(
        message_id=EntityId.from_string(row["message_id"]),
        event=event_from_row(row),
        topic=row["topic"],
        state=OutboxState(row["state"]),
        attempts=row["attempts"],
        next_attempt_at=as_utc(row["next_attempt_at"]),
        lease_expires_at=None
        if row["lease_expires_at"] is None
        else as_utc(row["lease_expires_at"]),
        delivered_at=None if row["delivered_at"] is None else as_utc(row["delivered_at"]),
        last_error_code=row["last_error_code"],
        revision=row["revision"],
        created_at=as_utc(row["created_at"]),
    )
