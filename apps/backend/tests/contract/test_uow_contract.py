"""Shared semantic contract for in-memory and SQLite UnitOfWork adapters."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config

from alpha_defense.application.ports import (
    EventEnvelope,
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    OutboxState,
    UnitOfWorkFactory,
)
from alpha_defense.application.shared import IdempotencyConflictError, StaleRevisionError
from alpha_defense.domain.shared import EntityId, ExecutionMode
from alpha_defense.infrastructure.observability import TransactionalAuditWriter
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from alpha_defense.infrastructure.runtime import (
    OutboxDispatcher,
    TransactionalEventSink,
    fingerprint_command,
    fingerprint_principal,
)

BACKEND_ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)


class FrozenClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def now_utc(self) -> datetime:
        return self.now

    def monotonic_ms(self) -> int:
        return 0


class FixedIdGenerator:
    def __init__(self, value: EntityId) -> None:
        self._value = value

    def new_id(self) -> EntityId:
        return self._value


def entity_id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


def alembic_config(database_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


def migrate(database_path: Path, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_path), revision)


@pytest.fixture(params=["memory", "sqlite"])
def uow_factory(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[UnitOfWorkFactory]:
    if request.param == "memory":
        yield InMemoryUnitOfWorkFactory()
        return
    engine = create_sqlite_engine(tmp_path / "contract.db")
    migrate(tmp_path / "contract.db")
    yield SqlAlchemyUnitOfWorkFactory(engine)
    engine.dispose()


def make_scope(*, key: str = "command-key") -> IdempotencyScope:
    return IdempotencyScope(
        principal_fingerprint=fingerprint_principal(["actor", str(entity_id(1))]),
        session_id=entity_id(2),
        namespace_id=entity_id(3),
        method="POST",
        canonical_route="/api/v1/example",
        key=key,
    )


def make_idempotency_record(
    *,
    command: dict[str, object] | None = None,
    record_id: EntityId | None = None,
    resource_id: EntityId | None = None,
) -> IdempotencyRecord:
    normalized = command or {"amount_minor": 1500000, "currency": "RUB"}
    return IdempotencyRecord(
        record_id=record_id or entity_id(4),
        scope=make_scope(),
        command_hash=fingerprint_command(normalized),  # type: ignore[arg-type]
        resource_id=resource_id or entity_id(5),
        state=IdempotencyState.IN_PROGRESS,
        result=None,
        revision=0,
        created_at=NOW,
        updated_at=NOW,
    )


def make_event() -> EventEnvelope:
    return EventEnvelope(
        event_id=entity_id(6),
        event_type="warning.created",
        aggregate_id=entity_id(7),
        aggregate_revision=1,
        occurred_at=NOW,
        correlation_id=entity_id(8),
        causation_id=None,
        execution_mode=ExecutionMode.MOCK,
        payload={"warning_id": str(entity_id(7)), "severity": "high"},
    )


def add_audit_and_outbox(uow_factory: UnitOfWorkFactory) -> EntityId:
    event = make_event()
    with uow_factory() as uow:
        audit = TransactionalAuditWriter(uow.audit, FrozenClock())
        sink = TransactionalEventSink(uow.outbox, FrozenClock(), FixedIdGenerator(entity_id(9)))
        audit.append(
            event,
            actor_id=entity_id(1),
            session_id=entity_id(2),
            namespace_id=entity_id(3),
        )
        receipt = sink.append(event, topic="warning.delivery")
        uow.commit()
    return receipt.message_id


def test_rollback_leaves_no_partial_technical_records(uow_factory: UnitOfWorkFactory) -> None:
    event = make_event()
    record = make_idempotency_record()

    with pytest.raises(RuntimeError, match="abort command"), uow_factory() as uow:
        uow.idempotency.reserve(record)
        TransactionalAuditWriter(uow.audit, FrozenClock()).append(
            event,
            actor_id=entity_id(1),
            session_id=entity_id(2),
            namespace_id=entity_id(3),
        )
        TransactionalEventSink(uow.outbox, FrozenClock(), FixedIdGenerator(entity_id(9))).append(
            event, topic="warning.delivery"
        )
        raise RuntimeError("abort command")

    with uow_factory() as uow:
        assert uow.idempotency.get(record.scope) is None
        assert uow.audit.list_all() == ()
        assert uow.outbox.list_all() == ()


def test_same_key_and_body_replays_but_different_body_conflicts(
    uow_factory: UnitOfWorkFactory,
) -> None:
    original = make_idempotency_record()
    with uow_factory() as uow:
        first = uow.idempotency.reserve(original)
        uow.commit()

    retry = make_idempotency_record(record_id=entity_id(10), resource_id=entity_id(11))
    with uow_factory() as uow:
        replay = uow.idempotency.reserve(retry)
        uow.commit()

    conflicting = make_idempotency_record(
        command={"amount_minor": 999, "currency": "RUB"},
        record_id=entity_id(12),
        resource_id=entity_id(13),
    )
    with pytest.raises(IdempotencyConflictError), uow_factory() as uow:
        uow.idempotency.reserve(conflicting)

    assert first.is_new
    assert not replay.is_new
    assert replay.record.record_id == original.record_id
    assert replay.record.resource_id == original.resource_id


def test_compare_and_swap_allows_one_winner(uow_factory: UnitOfWorkFactory) -> None:
    original = make_idempotency_record()
    with uow_factory() as uow:
        uow.idempotency.reserve(original)
        uow.commit()

    first_update = original.finish(
        state=IdempotencyState.COMPLETED,
        result={"status": "created"},
        updated_at=NOW + timedelta(seconds=1),
    )
    second_update = original.finish(
        state=IdempotencyState.FAILED,
        result={"status": "failed"},
        updated_at=NOW + timedelta(seconds=1),
    )
    with uow_factory() as uow:
        uow.idempotency.save(first_update, expected_revision=0)
        uow.commit()
    with pytest.raises(StaleRevisionError), uow_factory() as uow:
        uow.idempotency.save(second_update, expected_revision=0)

    with uow_factory() as uow:
        stored = uow.idempotency.get(original.scope)
    assert stored is not None
    assert stored.state is IdempotencyState.COMPLETED
    assert stored.revision == 1


def test_audit_and_outbox_commit_atomically_and_dispatch(uow_factory: UnitOfWorkFactory) -> None:
    message_id = add_audit_and_outbox(uow_factory)
    delivered_events: list[EventEnvelope] = []
    dispatcher = OutboxDispatcher(uow_factory, FrozenClock())
    dispatcher.register("warning.delivery", delivered_events.append)

    report = dispatcher.dispatch_once()

    with uow_factory() as uow:
        audit_records = uow.audit.list_all()
        message = uow.outbox.get(message_id)
    assert len(audit_records) == 1
    assert message is not None
    assert message.state is OutboxState.DELIVERED
    assert message.attempts == 1
    assert delivered_events == [make_event()]
    assert report.claimed == report.delivered == 1
    assert report.rescheduled == report.missing_handlers == 0


def test_dispatch_failure_is_rescheduled_without_exception_text(
    uow_factory: UnitOfWorkFactory,
) -> None:
    message_id = add_audit_and_outbox(uow_factory)
    dispatcher = OutboxDispatcher(uow_factory, FrozenClock())

    def fail(_: EventEnvelope) -> None:
        raise RuntimeError("private provider response")

    dispatcher.register("warning.delivery", fail)
    report = dispatcher.dispatch_once()

    with uow_factory() as uow:
        message = uow.outbox.get(message_id)
    assert message is not None
    assert message.state is OutboxState.PENDING
    assert message.last_error_code == "handler_failed"
    assert message.next_attempt_at == NOW + timedelta(seconds=5)
    assert report.rescheduled == 1
