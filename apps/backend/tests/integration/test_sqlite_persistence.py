"""Migration, restart recovery, and real SQLite concurrency checks."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import sqlalchemy as sa
from alembic import command

from alpha_defense.application.ports import IdempotencyState, OutboxState
from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from alpha_defense.infrastructure.runtime import OutboxDispatcher
from tests.contract.test_uow_contract import (
    NOW,
    FrozenClock,
    add_audit_and_outbox,
    alembic_config,
    make_idempotency_record,
    migrate,
)


def test_migration_creates_only_technical_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "schema.db"
    migrate(database_path, "20260915_0001")
    config = alembic_config(database_path)
    engine = create_sqlite_engine(database_path)

    inspector = sa.inspect(engine)

    assert set(inspector.get_table_names()) == {
        "alembic_version",
        "audit_events",
        "idempotency_records",
        "outbox",
    }
    assert {index["name"] for index in inspector.get_indexes("outbox")} == {"ix_outbox_dispatch"}
    engine.dispose()

    command.downgrade(config, "base")
    downgraded_engine = create_sqlite_engine(database_path)
    assert set(sa.inspect(downgraded_engine).get_table_names()) == {"alembic_version"}
    downgraded_engine.dispose()

    command.upgrade(config, "head")
    command.check(config)
    current_engine = create_sqlite_engine(database_path)
    assert set(sa.inspect(current_engine).get_table_names()) == {
        "alembic_version",
        "audit_events",
        "consents",
        "idempotency_records",
        "incident_assessments",
        "incident_correlation_keys",
        "incident_observations",
        "incident_resolutions",
        "incidents",
        "namespace_pending_analyses",
        "namespace_risk_states",
        "observation_content",
        "observation_indicators",
        "observations",
        "outbox",
        "pre_sessions",
        "sessions",
        "threat_records",
        "threat_registry_state",
        "threat_snapshots",
        "users",
        "warnings",
    }
    assert {
        index["name"] for index in sa.inspect(current_engine).get_indexes("threat_records")
    } == {"ix_threat_records_lookup"}
    assert {index["name"] for index in sa.inspect(current_engine).get_indexes("observations")} == {
        "ix_observations_owner_occurred"
    }
    assert {
        index["name"] for index in sa.inspect(current_engine).get_indexes("observation_indicators")
    } == {"ix_observation_indicators_lookup"}
    assert {index["name"] for index in sa.inspect(current_engine).get_indexes("incidents")} == {
        "ix_incidents_scope_updated"
    }
    assert {
        index["name"]
        for index in sa.inspect(current_engine).get_indexes("incident_correlation_keys")
    } == {"ix_incident_correlation_keys_lookup"}
    current_engine.dispose()


def test_audit_and_expired_outbox_lease_survive_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "restart.db"
    migrate(database_path)
    first_engine = create_sqlite_engine(database_path)
    first_factory = SqlAlchemyUnitOfWorkFactory(first_engine)
    message_id = add_audit_and_outbox(first_factory)

    with first_factory() as uow:
        claimed = uow.outbox.claim_next(
            now=NOW,
            lease_expires_at=NOW + timedelta(seconds=30),
        )
        uow.commit()
    assert claimed is not None
    first_engine.dispose()

    second_engine = create_sqlite_engine(database_path)
    second_factory = SqlAlchemyUnitOfWorkFactory(second_engine)
    delivered_event_ids: list[str] = []
    dispatcher = OutboxDispatcher(second_factory, FrozenClock(NOW + timedelta(seconds=31)))
    dispatcher.register(
        "warning.delivery",
        lambda event: delivered_event_ids.append(str(event.event_id)),
    )

    report = dispatcher.dispatch_once()

    with second_factory() as uow:
        message = uow.outbox.get(message_id)
        audit_records = uow.audit.list_all()
    assert message is not None
    assert message.state is OutboxState.DELIVERED
    assert message.attempts == 2
    assert len(audit_records) == 1
    assert delivered_event_ids == [str(audit_records[0].event.event_id)]
    assert report.delivered == 1
    second_engine.dispose()


def test_sqlite_compare_and_swap_has_one_concurrent_winner(tmp_path: Path) -> None:
    database_path = tmp_path / "cas.db"
    migrate(database_path)
    engine = create_sqlite_engine(database_path)
    factory = SqlAlchemyUnitOfWorkFactory(engine)
    original = make_idempotency_record()
    with factory() as uow:
        uow.idempotency.reserve(original)
        uow.commit()

    def try_complete(state: IdempotencyState) -> str:
        candidate = original.finish(
            state=state,
            result={"state": state.value},
            updated_at=NOW + timedelta(seconds=1),
        )
        try:
            with factory() as uow:
                uow.idempotency.save(candidate, expected_revision=0)
                uow.commit()
        except StaleRevisionError:
            return "stale"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                try_complete,
                [IdempotencyState.COMPLETED, IdempotencyState.FAILED],
            )
        )

    assert sorted(outcomes) == ["saved", "stale"]
    with factory() as uow:
        stored = uow.idempotency.get(original.scope)
    assert stored is not None
    assert stored.revision == 1
    engine.dispose()
