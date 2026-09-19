"""Read the current registry freshness without treating absence as no match."""

from __future__ import annotations

from alpha_defense.application.ports import Clock, ThreatUnitOfWorkFactory
from alpha_defense.application.threats.dto import RegistryAvailability, RegistryStatusView


class GetThreatRegistryStatus:
    def __init__(self, *, unit_of_work: ThreatUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    def execute(self) -> RegistryStatusView:
        with self._unit_of_work() as uow:
            snapshot = uow.threat_registry.get_current()
        if snapshot is None:
            return RegistryStatusView(
                availability=RegistryAvailability.UNAVAILABLE,
                snapshot_id=None,
                snapshot_version=None,
                source_versions=(),
                published_at=None,
                valid_until=None,
                record_count=0,
            )
        availability = (
            RegistryAvailability.READY
            if snapshot.is_available_at(self._clock.now_utc())
            else RegistryAvailability.EXPIRED
        )
        return RegistryStatusView(
            availability=availability,
            snapshot_id=snapshot.snapshot_id,
            snapshot_version=snapshot.version,
            source_versions=tuple(
                f"{item.source}@{item.version}" for item in snapshot.source_versions
            ),
            published_at=snapshot.published_at,
            valid_until=snapshot.valid_until,
            record_count=snapshot.record_count,
        )
