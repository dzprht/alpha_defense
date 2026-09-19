"""SQLAlchemy implementations of the technical repository ports."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult, Result
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.ports import (
    AuditRecord,
    IdempotencyRecord,
    IdempotencyReservation,
    IdempotencyScope,
    OutboxMessage,
    OutboxState,
)
from alpha_defense.application.shared import (
    IdempotencyConflictError,
    ServiceUnavailableError,
    StaleRevisionError,
)
from alpha_defense.domain.identity import (
    ConsentScope,
    ConsentSnapshot,
    DemoSession,
    PreSession,
    SyntheticUser,
)
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.persistence.sqlalchemy.mappers import (
    audit_from_row,
    audit_values,
    consent_from_row,
    consent_values,
    idempotency_from_row,
    idempotency_values,
    outbox_from_row,
    outbox_values,
    pre_session_from_row,
    pre_session_values,
    session_from_row,
    session_values,
    user_from_row,
    user_values,
)
from alpha_defense.infrastructure.persistence.sqlalchemy.schema import (
    audit_events,
    consents,
    idempotency_records,
    outbox,
    pre_sessions,
    sessions,
    users,
)


def _scope_condition(scope: IdempotencyScope) -> sa.ColumnElement[bool]:
    return sa.and_(
        idempotency_records.c.principal_fingerprint == scope.principal_fingerprint,
        idempotency_records.c.session_id
        == ("" if scope.session_id is None else str(scope.session_id)),
        idempotency_records.c.namespace_id
        == ("" if scope.namespace_id is None else str(scope.namespace_id)),
        idempotency_records.c.method == scope.method,
        idempotency_records.c.canonical_route == scope.canonical_route,
        idempotency_records.c.idempotency_key == scope.key,
    )


def _rowcount(result: Result[Any]) -> int:
    return cast(CursorResult[Any], result).rowcount


def _execute(session: Session, statement: Any) -> Result[Any]:
    try:
        return session.execute(statement)
    except IntegrityError as exc:
        raise ValueError("persistence constraint rejected the record") from exc
    except SQLAlchemyError as exc:
        raise ServiceUnavailableError("Local persistence is unavailable") from exc


class SqlAlchemyIdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, scope: IdempotencyScope) -> IdempotencyRecord | None:
        row = (
            _execute(
                self._session,
                sa.select(idempotency_records).where(_scope_condition(scope)),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else idempotency_from_row(row)

    def get_by_id(self, record_id: EntityId) -> IdempotencyRecord | None:
        row = (
            _execute(
                self._session,
                sa.select(idempotency_records).where(
                    idempotency_records.c.record_id == str(record_id)
                ),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else idempotency_from_row(row)

    def reserve(self, record: IdempotencyRecord) -> IdempotencyReservation:
        statement = sqlite_insert(idempotency_records).values(idempotency_values(record))
        result = _execute(self._session, statement.on_conflict_do_nothing())
        if _rowcount(result) == 1:
            return IdempotencyReservation(record=record, is_new=True)
        existing = self.get(record.scope)
        if existing is None:
            raise ValueError("idempotency record_id already exists")
        if existing.command_hash != record.command_hash:
            raise IdempotencyConflictError(
                "The idempotency key was already used with a different command"
            )
        return IdempotencyReservation(record=existing, is_new=False)

    def save(self, record: IdempotencyRecord, *, expected_revision: int) -> None:
        current = self.get_by_id(record.record_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Idempotency record revision is stale")
        if record.revision != expected_revision + 1:
            raise StaleRevisionError("Idempotency record must advance revision by one")
        if (
            current.scope != record.scope
            or current.command_hash != record.command_hash
            or current.resource_id != record.resource_id
            or current.created_at != record.created_at
        ):
            raise ValueError("immutable idempotency fields cannot be changed")
        result = _execute(
            self._session,
            sa.update(idempotency_records)
            .where(
                idempotency_records.c.record_id == str(record.record_id),
                idempotency_records.c.revision == expected_revision,
            )
            .values(
                state=record.state.value,
                result_json=idempotency_values(record)["result_json"],
                revision=record.revision,
                updated_at=record.updated_at,
            ),
        )
        if _rowcount(result) != 1:
            raise StaleRevisionError("Idempotency record revision is stale")


class SqlAlchemyIdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_user(self, user: SyntheticUser) -> None:
        result = _execute(
            self._session,
            sqlite_insert(users).values(user_values(user)).on_conflict_do_nothing(),
        )
        if _rowcount(result) == 1:
            return
        if self.get_user(user.user_id) != user:
            raise ValueError("user_id already exists with different data")

    def get_user(self, user_id: EntityId) -> SyntheticUser | None:
        row = (
            _execute(
                self._session,
                sa.select(users).where(users.c.user_id == str(user_id)),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else user_from_row(row)

    def add_pre_session(self, pre_session: PreSession) -> None:
        result = _execute(
            self._session,
            sqlite_insert(pre_sessions)
            .values(pre_session_values(pre_session))
            .on_conflict_do_nothing(),
        )
        if _rowcount(result) == 1:
            return
        existing = self.get_pre_session_by_fingerprint(pre_session.token_fingerprint)
        if existing != pre_session:
            raise ValueError("pre-session token or id already exists with different data")

    def get_pre_session_by_fingerprint(self, token_fingerprint: str) -> PreSession | None:
        row = (
            _execute(
                self._session,
                sa.select(pre_sessions).where(
                    pre_sessions.c.token_fingerprint == token_fingerprint
                ),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else pre_session_from_row(row)

    def save_pre_session(
        self,
        pre_session: PreSession,
        *,
        expected_consumed_session_id: EntityId | None,
    ) -> None:
        expected = (
            pre_sessions.c.consumed_session_id.is_(None)
            if expected_consumed_session_id is None
            else pre_sessions.c.consumed_session_id == str(expected_consumed_session_id)
        )
        result = _execute(
            self._session,
            sa.update(pre_sessions)
            .where(
                pre_sessions.c.pre_session_id == str(pre_session.pre_session_id),
                expected,
            )
            .values(
                consumed_session_id=(
                    None
                    if pre_session.consumed_session_id is None
                    else str(pre_session.consumed_session_id)
                )
            ),
        )
        if _rowcount(result) != 1:
            raise StaleRevisionError("Pre-session was already consumed")

    def add_session(self, session: DemoSession) -> None:
        result = _execute(
            self._session,
            sqlite_insert(sessions).values(session_values(session)).on_conflict_do_nothing(),
        )
        if _rowcount(result) == 1:
            return
        if self.get_session(session.session_id) != session:
            raise ValueError("session id, token, or namespace already exists")

    def get_session(self, session_id: EntityId) -> DemoSession | None:
        row = (
            _execute(
                self._session,
                sa.select(sessions).where(sessions.c.session_id == str(session_id)),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else session_from_row(row)

    def get_session_by_fingerprint(self, token_fingerprint: str) -> DemoSession | None:
        row = (
            _execute(
                self._session,
                sa.select(sessions).where(sessions.c.token_fingerprint == token_fingerprint),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else session_from_row(row)

    def save_session(self, session: DemoSession, *, expected_consent_revision: int) -> None:
        current = self.get_session(session.session_id)
        if current is None or current.consent_revision != expected_consent_revision:
            raise StaleRevisionError("Session consent revision is stale")
        if (
            current.user_id != session.user_id
            or current.manual_namespace_id != session.manual_namespace_id
            or current.roles != session.roles
            or current.token_fingerprint != session.token_fingerprint
            or current.created_at != session.created_at
            or current.expires_at != session.expires_at
        ):
            raise ValueError("immutable session fields cannot be changed")
        if session.consent_revision != expected_consent_revision + 1:
            raise StaleRevisionError("Session consent revision must advance by one")
        result = _execute(
            self._session,
            sa.update(sessions)
            .where(
                sessions.c.session_id == str(session.session_id),
                sessions.c.consent_revision == expected_consent_revision,
            )
            .values(consent_revision=session.consent_revision),
        )
        if _rowcount(result) != 1:
            raise StaleRevisionError("Session consent revision is stale")

    def add_consent(self, consent: ConsentSnapshot) -> None:
        result = _execute(
            self._session,
            sqlite_insert(consents).values(consent_values(consent)).on_conflict_do_nothing(),
        )
        if _rowcount(result) == 1:
            return
        if self.get_consent(consent.user_id, consent.scope) != consent:
            raise ValueError("consent scope already exists with different data")

    def get_consent(
        self,
        user_id: EntityId,
        scope: ConsentScope,
    ) -> ConsentSnapshot | None:
        row = (
            _execute(
                self._session,
                sa.select(consents).where(
                    consents.c.user_id == str(user_id),
                    consents.c.scope == scope.value,
                ),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else consent_from_row(row)

    def list_consents(self, user_id: EntityId) -> tuple[ConsentSnapshot, ...]:
        rows = _execute(
            self._session,
            sa.select(consents)
            .where(consents.c.user_id == str(user_id))
            .order_by(consents.c.scope),
        ).mappings()
        return tuple(consent_from_row(row) for row in rows)

    def save_consent(self, consent: ConsentSnapshot, *, expected_revision: int) -> None:
        result = _execute(
            self._session,
            sa.update(consents)
            .where(
                consents.c.user_id == str(consent.user_id),
                consents.c.scope == consent.scope.value,
                consents.c.revision == expected_revision,
            )
            .values(
                status=consent.status.value,
                revision=consent.revision,
                changed_at=consent.changed_at,
            ),
        )
        if _rowcount(result) != 1:
            raise StaleRevisionError("Consent revision is stale")


class SqlAlchemyAuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, record: AuditRecord) -> None:
        statement = sqlite_insert(audit_events).values(audit_values(record))
        result = _execute(
            self._session,
            statement.on_conflict_do_nothing(index_elements=["event_id"]),
        )
        if _rowcount(result) == 1:
            return
        existing = self.get(record.event.event_id)
        if existing != record:
            raise ValueError("audit event_id already exists with different data")

    def get(self, event_id: EntityId) -> AuditRecord | None:
        row = (
            _execute(
                self._session,
                sa.select(audit_events).where(audit_events.c.event_id == str(event_id)),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else audit_from_row(row)

    def list_all(self) -> tuple[AuditRecord, ...]:
        rows = _execute(
            self._session,
            sa.select(audit_events).order_by(audit_events.c.recorded_at, audit_events.c.event_id),
        ).mappings()
        return tuple(audit_from_row(row) for row in rows)


class SqlAlchemyOutboxRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, message: OutboxMessage) -> None:
        statement = sqlite_insert(outbox).values(outbox_values(message)).on_conflict_do_nothing()
        result = _execute(self._session, statement)
        if _rowcount(result) == 1:
            return
        existing = self.get(message.message_id)
        if existing is None:
            row = (
                _execute(
                    self._session,
                    sa.select(outbox).where(
                        outbox.c.event_id == str(message.event.event_id),
                        outbox.c.topic == message.topic,
                    ),
                )
                .mappings()
                .one_or_none()
            )
            existing = None if row is None else outbox_from_row(row)
        if existing != message:
            raise ValueError("outbox message or event/topic already exists with different data")

    def get(self, message_id: EntityId) -> OutboxMessage | None:
        row = (
            _execute(
                self._session,
                sa.select(outbox).where(outbox.c.message_id == str(message_id)),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else outbox_from_row(row)

    def list_all(self) -> tuple[OutboxMessage, ...]:
        rows = _execute(
            self._session,
            sa.select(outbox).order_by(outbox.c.created_at, outbox.c.message_id),
        ).mappings()
        return tuple(outbox_from_row(row) for row in rows)

    def claim_next(self, *, now: datetime, lease_expires_at: datetime) -> OutboxMessage | None:
        if lease_expires_at <= now:
            raise ValueError("lease_expires_at must be later than now")
        eligible = sa.or_(
            sa.and_(outbox.c.state == OutboxState.PENDING.value, outbox.c.next_attempt_at <= now),
            sa.and_(
                outbox.c.state == OutboxState.PROCESSING.value,
                outbox.c.lease_expires_at.is_not(None),
                outbox.c.lease_expires_at <= now,
            ),
        )
        rows = _execute(
            self._session,
            sa.select(outbox)
            .where(eligible)
            .order_by(outbox.c.next_attempt_at, outbox.c.message_id)
            .limit(20),
        ).mappings()
        for row in rows:
            current = outbox_from_row(row)
            claimed = replace(
                current,
                state=OutboxState.PROCESSING,
                attempts=current.attempts + 1,
                lease_expires_at=lease_expires_at,
                delivered_at=None,
                last_error_code=None,
                revision=current.revision + 1,
            )
            result = _execute(
                self._session,
                sa.update(outbox)
                .where(
                    outbox.c.message_id == str(current.message_id),
                    outbox.c.revision == current.revision,
                    eligible,
                )
                .values(
                    state=claimed.state.value,
                    attempts=claimed.attempts,
                    lease_expires_at=claimed.lease_expires_at,
                    delivered_at=None,
                    last_error_code=None,
                    revision=claimed.revision,
                ),
            )
            if _rowcount(result) == 1:
                return claimed
        return None

    def mark_delivered(
        self,
        message_id: EntityId,
        *,
        expected_revision: int,
        delivered_at: datetime,
    ) -> OutboxMessage:
        current = self._get_processing(message_id, expected_revision=expected_revision)
        updated = replace(
            current,
            state=OutboxState.DELIVERED,
            lease_expires_at=None,
            delivered_at=delivered_at,
            last_error_code=None,
            revision=current.revision + 1,
        )
        self._save_status(updated, expected_revision=expected_revision)
        return updated

    def reschedule(
        self,
        message_id: EntityId,
        *,
        expected_revision: int,
        next_attempt_at: datetime,
        error_code: str,
    ) -> OutboxMessage:
        current = self._get_processing(message_id, expected_revision=expected_revision)
        updated = replace(
            current,
            state=OutboxState.PENDING,
            next_attempt_at=next_attempt_at,
            lease_expires_at=None,
            delivered_at=None,
            last_error_code=error_code,
            revision=current.revision + 1,
        )
        self._save_status(updated, expected_revision=expected_revision)
        return updated

    def _get_processing(self, message_id: EntityId, *, expected_revision: int) -> OutboxMessage:
        current = self.get(message_id)
        if (
            current is None
            or current.revision != expected_revision
            or current.state is not OutboxState.PROCESSING
        ):
            raise StaleRevisionError("Outbox message revision or state is stale")
        return current

    def _save_status(self, message: OutboxMessage, *, expected_revision: int) -> None:
        result = _execute(
            self._session,
            sa.update(outbox)
            .where(
                outbox.c.message_id == str(message.message_id),
                outbox.c.revision == expected_revision,
                outbox.c.state == OutboxState.PROCESSING.value,
            )
            .values(
                state=message.state.value,
                next_attempt_at=message.next_attempt_at,
                lease_expires_at=message.lease_expires_at,
                delivered_at=message.delivered_at,
                last_error_code=message.last_error_code,
                revision=message.revision,
            ),
        )
        if _rowcount(result) != 1:
            raise StaleRevisionError("Outbox message revision or state is stale")
