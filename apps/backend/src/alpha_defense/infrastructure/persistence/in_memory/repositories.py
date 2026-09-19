"""Technical repositories backed by one transactional state snapshot."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from alpha_defense.application.ports import (
    AuditRecord,
    IdempotencyRecord,
    IdempotencyReservation,
    IdempotencyScope,
    OutboxMessage,
    OutboxState,
)
from alpha_defense.application.shared import IdempotencyConflictError, StaleRevisionError
from alpha_defense.domain.identity import (
    ConsentScope,
    ConsentSnapshot,
    DemoSession,
    PreSession,
    SyntheticUser,
)
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryState


def _assert_idempotency_update(
    current: IdempotencyRecord,
    updated: IdempotencyRecord,
    *,
    expected_revision: int,
) -> None:
    if current.revision != expected_revision or updated.revision != expected_revision + 1:
        raise StaleRevisionError("Idempotency record revision is stale")
    if (
        current.record_id != updated.record_id
        or current.scope != updated.scope
        or current.command_hash != updated.command_hash
        or current.resource_id != updated.resource_id
        or current.created_at != updated.created_at
    ):
        raise ValueError("immutable idempotency fields cannot be changed")


class InMemoryIdempotencyRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get(self, scope: IdempotencyScope) -> IdempotencyRecord | None:
        record_id = self._state.idempotency_scopes.get(scope)
        return None if record_id is None else self._state.idempotency_records[record_id]

    def get_by_id(self, record_id: EntityId) -> IdempotencyRecord | None:
        return self._state.idempotency_records.get(record_id)

    def reserve(self, record: IdempotencyRecord) -> IdempotencyReservation:
        existing = self.get(record.scope)
        if existing is not None:
            if existing.command_hash != record.command_hash:
                raise IdempotencyConflictError(
                    "The idempotency key was already used with a different command"
                )
            return IdempotencyReservation(record=existing, is_new=False)
        if record.record_id in self._state.idempotency_records:
            raise ValueError("idempotency record_id already exists")
        self._state.idempotency_records[record.record_id] = record
        self._state.idempotency_scopes[record.scope] = record.record_id
        return IdempotencyReservation(record=record, is_new=True)

    def save(self, record: IdempotencyRecord, *, expected_revision: int) -> None:
        current = self._state.idempotency_records.get(record.record_id)
        if current is None:
            raise StaleRevisionError("Idempotency record does not exist")
        _assert_idempotency_update(current, record, expected_revision=expected_revision)
        self._state.idempotency_records[record.record_id] = record


class InMemoryIdentityRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def add_user(self, user: SyntheticUser) -> None:
        existing = self._state.users.get(user.user_id)
        if existing is not None and existing != user:
            raise ValueError("user_id already exists with different data")
        self._state.users[user.user_id] = user

    def get_user(self, user_id: EntityId) -> SyntheticUser | None:
        return self._state.users.get(user_id)

    def add_pre_session(self, pre_session: PreSession) -> None:
        existing_id = self._state.pre_session_tokens.get(pre_session.token_fingerprint)
        existing = self._state.pre_sessions.get(pre_session.pre_session_id)
        if existing == pre_session or (
            existing_id is not None and self._state.pre_sessions[existing_id] == pre_session
        ):
            return
        if existing is not None or existing_id is not None:
            raise ValueError("pre-session token or id already exists")
        self._state.pre_sessions[pre_session.pre_session_id] = pre_session
        self._state.pre_session_tokens[pre_session.token_fingerprint] = pre_session.pre_session_id

    def get_pre_session_by_fingerprint(self, token_fingerprint: str) -> PreSession | None:
        pre_session_id = self._state.pre_session_tokens.get(token_fingerprint)
        return None if pre_session_id is None else self._state.pre_sessions[pre_session_id]

    def save_pre_session(
        self,
        pre_session: PreSession,
        *,
        expected_consumed_session_id: EntityId | None,
    ) -> None:
        current = self._state.pre_sessions.get(pre_session.pre_session_id)
        if current is None or current.consumed_session_id != expected_consumed_session_id:
            raise StaleRevisionError("Pre-session was already consumed")
        if (
            current.token_fingerprint != pre_session.token_fingerprint
            or current.created_at != pre_session.created_at
            or current.expires_at != pre_session.expires_at
        ):
            raise ValueError("immutable pre-session fields cannot be changed")
        self._state.pre_sessions[pre_session.pre_session_id] = pre_session

    def add_session(self, session: DemoSession) -> None:
        token_owner = self._state.session_tokens.get(session.token_fingerprint)
        namespace_owner = self._state.session_namespaces.get(session.manual_namespace_id)
        existing = self._state.sessions.get(session.session_id)
        if existing == session:
            return
        if existing is not None or token_owner is not None or namespace_owner is not None:
            raise ValueError("session id, token, or namespace already exists")
        if session.user_id not in self._state.users:
            raise ValueError("session user does not exist")
        self._state.sessions[session.session_id] = session
        self._state.session_tokens[session.token_fingerprint] = session.session_id
        self._state.session_namespaces[session.manual_namespace_id] = session.session_id

    def get_session(self, session_id: EntityId) -> DemoSession | None:
        return self._state.sessions.get(session_id)

    def get_session_by_fingerprint(self, token_fingerprint: str) -> DemoSession | None:
        session_id = self._state.session_tokens.get(token_fingerprint)
        return None if session_id is None else self._state.sessions[session_id]

    def save_session(self, session: DemoSession, *, expected_consent_revision: int) -> None:
        current = self._state.sessions.get(session.session_id)
        if current is None or current.consent_revision != expected_consent_revision:
            raise StaleRevisionError("Session consent revision is stale")
        if session.consent_revision != expected_consent_revision + 1:
            raise StaleRevisionError("Session consent revision must advance by one")
        if replace(current, consent_revision=session.consent_revision) != session:
            raise ValueError("immutable session fields cannot be changed")
        self._state.sessions[session.session_id] = session

    def add_consent(self, consent: ConsentSnapshot) -> None:
        key = (consent.user_id, consent.scope)
        existing = self._state.consents.get(key)
        if existing is not None and existing != consent:
            raise ValueError("consent scope already exists with different data")
        if consent.user_id not in self._state.users:
            raise ValueError("consent user does not exist")
        self._state.consents[key] = consent

    def get_consent(
        self,
        user_id: EntityId,
        scope: ConsentScope,
    ) -> ConsentSnapshot | None:
        return self._state.consents.get((user_id, scope))

    def list_consents(self, user_id: EntityId) -> tuple[ConsentSnapshot, ...]:
        return tuple(
            sorted(
                (
                    consent
                    for (owner_id, _), consent in self._state.consents.items()
                    if owner_id == user_id
                ),
                key=lambda consent: consent.scope.value,
            )
        )

    def save_consent(self, consent: ConsentSnapshot, *, expected_revision: int) -> None:
        key = (consent.user_id, consent.scope)
        current = self._state.consents.get(key)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Consent revision is stale")
        if consent.revision <= expected_revision:
            raise StaleRevisionError("Consent revision must advance")
        self._state.consents[key] = consent


class InMemoryAuditRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def append(self, record: AuditRecord) -> None:
        event_id = record.event.event_id
        existing = self._state.audit_events.get(event_id)
        if existing is not None and existing != record:
            raise ValueError("audit event_id already exists with different data")
        self._state.audit_events[event_id] = record

    def get(self, event_id: EntityId) -> AuditRecord | None:
        return self._state.audit_events.get(event_id)

    def list_all(self) -> tuple[AuditRecord, ...]:
        return tuple(
            sorted(
                self._state.audit_events.values(),
                key=lambda record: (record.recorded_at, str(record.event.event_id)),
            )
        )


class InMemoryOutboxRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def add(self, message: OutboxMessage) -> None:
        event_key = (message.event.event_id, message.topic)
        existing = self._state.outbox_messages.get(message.message_id)
        if existing == message:
            return
        if existing is not None:
            raise ValueError("outbox message_id already exists")
        queued_id = self._state.outbox_events.get(event_key)
        if queued_id is not None:
            if self._state.outbox_messages[queued_id] == message:
                return
            raise ValueError("event is already queued for this topic")
        self._state.outbox_messages[message.message_id] = message
        self._state.outbox_events[event_key] = message.message_id

    def get(self, message_id: EntityId) -> OutboxMessage | None:
        return self._state.outbox_messages.get(message_id)

    def list_all(self) -> tuple[OutboxMessage, ...]:
        return tuple(
            sorted(
                self._state.outbox_messages.values(),
                key=lambda message: (message.created_at, str(message.message_id)),
            )
        )

    def claim_next(self, *, now: datetime, lease_expires_at: datetime) -> OutboxMessage | None:
        if lease_expires_at <= now:
            raise ValueError("lease_expires_at must be later than now")
        eligible = [
            message
            for message in self._state.outbox_messages.values()
            if (
                (message.state is OutboxState.PENDING and message.next_attempt_at <= now)
                or (
                    message.state is OutboxState.PROCESSING
                    and message.lease_expires_at is not None
                    and message.lease_expires_at <= now
                )
            )
        ]
        if not eligible:
            return None
        current = min(eligible, key=lambda item: (item.next_attempt_at, str(item.message_id)))
        claimed = replace(
            current,
            state=OutboxState.PROCESSING,
            attempts=current.attempts + 1,
            lease_expires_at=lease_expires_at,
            delivered_at=None,
            last_error_code=None,
            revision=current.revision + 1,
        )
        self._state.outbox_messages[current.message_id] = claimed
        return claimed

    def mark_delivered(
        self,
        message_id: EntityId,
        *,
        expected_revision: int,
        delivered_at: datetime,
    ) -> OutboxMessage:
        current = self._processing(message_id, expected_revision=expected_revision)
        delivered = replace(
            current,
            state=OutboxState.DELIVERED,
            lease_expires_at=None,
            delivered_at=delivered_at,
            last_error_code=None,
            revision=current.revision + 1,
        )
        self._state.outbox_messages[message_id] = delivered
        return delivered

    def reschedule(
        self,
        message_id: EntityId,
        *,
        expected_revision: int,
        next_attempt_at: datetime,
        error_code: str,
    ) -> OutboxMessage:
        current = self._processing(message_id, expected_revision=expected_revision)
        pending = replace(
            current,
            state=OutboxState.PENDING,
            next_attempt_at=next_attempt_at,
            lease_expires_at=None,
            delivered_at=None,
            last_error_code=error_code,
            revision=current.revision + 1,
        )
        self._state.outbox_messages[message_id] = pending
        return pending

    def _processing(self, message_id: EntityId, *, expected_revision: int) -> OutboxMessage:
        current = self._state.outbox_messages.get(message_id)
        if (
            current is None
            or current.revision != expected_revision
            or current.state is not OutboxState.PROCESSING
        ):
            raise StaleRevisionError("Outbox message revision or state is stale")
        return current
