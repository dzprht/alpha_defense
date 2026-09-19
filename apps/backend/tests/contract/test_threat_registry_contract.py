"""Common threat registry behavior for in-memory and SQLite adapters."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from alpha_defense.application.ports import (
    ThreatBatch,
    ThreatFeedRecord,
    ThreatUnitOfWorkFactory,
)
from alpha_defense.application.shared import ValidationError
from alpha_defense.application.threats import (
    GetThreatRegistryStatus,
    LookupThreatIndicators,
    RefreshThreatRegistry,
    RegistryAvailability,
    ThreatLookupOutcome,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode
from alpha_defense.domain.threats import IndicatorType, ThreatIndicator
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from tests.contract.test_uow_contract import FrozenClock, migrate

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
SOURCE = "alpha-defense-synthetic"


class SequentialIdGenerator:
    def __init__(self) -> None:
        self._value = 100

    def new_id(self) -> EntityId:
        self._value += 1
        return EntityId(UUID(int=self._value))


@dataclass(slots=True)
class MutableFeed:
    batch: ThreatBatch

    def fetch(self, source: str) -> ThreatBatch:
        assert source == SOURCE
        return self.batch


@pytest.fixture(params=["memory", "sqlite"])
def threat_uow_factory(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[ThreatUnitOfWorkFactory]:
    if request.param == "memory":
        yield InMemoryUnitOfWorkFactory()
        return
    database_path = tmp_path / "threat-contract.db"
    migrate(database_path)
    engine = create_sqlite_engine(database_path)
    yield SqlAlchemyUnitOfWorkFactory(engine)
    engine.dispose()


def _record(
    record_id: str,
    indicator_type: str,
    value: str,
    status: str,
    *,
    expires_at: datetime | None = None,
) -> ThreatFeedRecord:
    expiry = expires_at or NOW + timedelta(days=2)
    observed_at = NOW - timedelta(hours=1)
    if status == "expired":
        observed_at = NOW - timedelta(minutes=30)
        expiry = NOW - timedelta(hours=1)
    return ThreatFeedRecord(
        source_record_id=record_id,
        indicator_type=indicator_type,
        value=value,
        normalization_version="indicator-v1",
        status=status,
        first_seen_at=NOW - timedelta(days=2),
        observed_at=observed_at,
        expires_at=expiry,
        evidence_ref=f"synthetic://threats/{record_id}",
        verification_source="synthetic_review",
    )


def _batch(version: str = "1.0.0") -> ThreatBatch:
    return ThreatBatch(
        source=SOURCE,
        source_version=version,
        generated_at=NOW - timedelta(minutes=15),
        valid_until=NOW + timedelta(days=1),
        records=(
            _record("active-url", "url", "https://fraud.test/pay", "active"),
            _record("revoked-domain", "domain", "revoked.test", "revoked"),
            _record("expired-ip", "ip", "192.0.2.10", "expired"),
            _record("unverified-phone", "phone", "+70000000001", "unverified"),
        ),
    )


def _services(
    factory: ThreatUnitOfWorkFactory,
    feed: MutableFeed,
) -> tuple[RefreshThreatRegistry, LookupThreatIndicators, GetThreatRegistryStatus]:
    clock = FrozenClock(NOW)
    return (
        RefreshThreatRegistry(
            source=SOURCE,
            feed=feed,
            unit_of_work=factory,
            clock=clock,
            id_generator=SequentialIdGenerator(),
            execution_mode=ExecutionMode.MOCK,
        ),
        LookupThreatIndicators(unit_of_work=factory, clock=clock),
        GetThreatRegistryStatus(unit_of_work=factory, clock=clock),
    )


def test_active_match_and_non_active_records_have_distinct_outcomes(
    threat_uow_factory: ThreatUnitOfWorkFactory,
) -> None:
    feed = MutableFeed(_batch())
    refresh, lookup, status = _services(threat_uow_factory, feed)
    indicator = ThreatIndicator.from_raw(IndicatorType.URL, "https://fraud.test/pay")

    before = lookup.execute((indicator,))[0]
    published = refresh.execute()
    results = lookup.execute(
        (
            indicator,
            ThreatIndicator.from_raw(IndicatorType.DOMAIN, "revoked.test"),
            ThreatIndicator.from_raw(IndicatorType.IP, "192.0.2.10"),
            ThreatIndicator.from_raw(IndicatorType.PHONE, "+70000000001"),
            ThreatIndicator.from_raw(IndicatorType.DOMAIN, "unknown.test"),
        )
    )

    assert before.outcome is ThreatLookupOutcome.UNAVAILABLE
    assert published.published
    assert results[0].outcome is ThreatLookupOutcome.MATCH
    assert len(results[0].matches) == 1
    assert all(result.outcome is ThreatLookupOutcome.NO_MATCH for result in results[1:])
    assert status.execute().availability is RegistryAvailability.READY


def test_repeat_refresh_is_idempotent_and_version_change_is_visible(
    threat_uow_factory: ThreatUnitOfWorkFactory,
) -> None:
    feed = MutableFeed(_batch())
    refresh, lookup, _ = _services(threat_uow_factory, feed)

    first = refresh.execute()
    repeated = refresh.execute()
    first_lookup = lookup.execute(
        (ThreatIndicator.from_raw(IndicatorType.URL, "https://fraud.test/pay"),)
    )[0]
    feed.batch = _batch("1.1.0")
    second = refresh.execute()
    second_lookup = lookup.execute(
        (ThreatIndicator.from_raw(IndicatorType.URL, "https://fraud.test/pay"),)
    )[0]

    with threat_uow_factory() as uow:
        versions = tuple(uow.threat_registry.list_versions())
        audits = tuple(uow.audit.list_all())
    assert first.published
    assert not repeated.published
    assert second.published
    assert first_lookup.snapshot_version == first.snapshot_version
    assert second_lookup.snapshot_version == second.snapshot_version
    assert second.snapshot_version != first.snapshot_version
    assert len(versions) == 2
    assert [record.event.event_type for record in audits] == [
        "registry.updated",
        "registry.updated",
    ]


def test_expired_registry_is_unavailable_not_a_negative_match(
    threat_uow_factory: ThreatUnitOfWorkFactory,
) -> None:
    feed = MutableFeed(_batch())
    refresh, _, _ = _services(threat_uow_factory, feed)
    refresh.execute()
    expired_clock = FrozenClock(NOW + timedelta(days=2))
    lookup = LookupThreatIndicators(unit_of_work=threat_uow_factory, clock=expired_clock)
    status = GetThreatRegistryStatus(unit_of_work=threat_uow_factory, clock=expired_clock)

    result = lookup.execute((ThreatIndicator.from_raw(IndicatorType.DOMAIN, "unknown.test"),))[0]

    assert result.outcome is ThreatLookupOutcome.UNAVAILABLE
    assert result.reason_code == "registry_expired"
    assert result.snapshot_id is not None
    assert result.snapshot_version is not None
    assert status.execute().availability is RegistryAvailability.EXPIRED


def test_bad_batch_does_not_replace_last_valid_snapshot(
    threat_uow_factory: ThreatUnitOfWorkFactory,
) -> None:
    feed = MutableFeed(_batch())
    refresh, _, status = _services(threat_uow_factory, feed)
    first = refresh.execute()
    good = feed.batch.records[0]
    duplicate = ThreatFeedRecord(
        source_record_id="duplicate-url",
        indicator_type=good.indicator_type,
        value=good.value,
        normalization_version=good.normalization_version,
        status=good.status,
        first_seen_at=good.first_seen_at,
        observed_at=good.observed_at,
        expires_at=good.expires_at,
        evidence_ref="synthetic://threats/duplicate-url",
        verification_source=good.verification_source,
    )
    feed.batch = ThreatBatch(
        source=SOURCE,
        source_version="1.1.0",
        generated_at=feed.batch.generated_at,
        valid_until=feed.batch.valid_until,
        records=(*feed.batch.records, duplicate),
    )

    with pytest.raises(ValidationError):
        refresh.execute()

    current = status.execute()
    with threat_uow_factory() as uow:
        versions = tuple(uow.threat_registry.list_versions())
    assert current.snapshot_version == first.snapshot_version
    assert versions == (first.snapshot_version,)


def test_snapshot_and_current_pointer_roll_back_together(
    threat_uow_factory: ThreatUnitOfWorkFactory,
) -> None:
    feed = MutableFeed(_batch())
    refresh, _, status = _services(threat_uow_factory, feed)
    first = refresh.execute()

    with pytest.raises(RuntimeError, match="abort publication"), threat_uow_factory() as uow:
        current = uow.threat_registry.get_current()
        assert current is not None
        candidate = replace(
            current,
            snapshot_id=EntityId(UUID(int=999)),
            version="rollback-probe",
            content_sha256="b" * 64,
        )
        uow.threat_registry.publish(candidate, expected_current_id=current.snapshot_id)
        raise RuntimeError("abort publication")

    with threat_uow_factory() as uow:
        assert uow.threat_registry.get_by_version("rollback-probe") is None
    assert status.execute().snapshot_version == first.snapshot_version
