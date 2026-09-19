"""Exact typed lookups against one immutable registry snapshot."""

from __future__ import annotations

from collections.abc import Sequence

from alpha_defense.application.ports import Clock, ThreatUnitOfWorkFactory
from alpha_defense.application.threats.dto import (
    ThreatLookupOutcome,
    ThreatLookupResult,
    ThreatMatch,
)
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import ThreatIndicator


class LookupThreatIndicators:
    def __init__(self, *, unit_of_work: ThreatUnitOfWorkFactory, clock: Clock) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    def execute(
        self,
        indicators: Sequence[ThreatIndicator],
    ) -> tuple[ThreatLookupResult, ...]:
        if not indicators or any(not isinstance(item, ThreatIndicator) for item in indicators):
            raise ValueError("indicators must contain at least one ThreatIndicator")
        now = self._clock.now_utc()
        with self._unit_of_work() as uow:
            snapshot = uow.threat_registry.get_current()
        if snapshot is None:
            return tuple(
                _unavailable(item, "registry_unavailable", snapshot_id=None, version=None)
                for item in indicators
            )
        if not snapshot.is_available_at(now):
            return tuple(
                _unavailable(
                    item,
                    "registry_expired",
                    snapshot_id=snapshot.snapshot_id,
                    version=snapshot.version,
                )
                for item in indicators
            )

        results: list[ThreatLookupResult] = []
        for indicator in indicators:
            matches = snapshot.active_matches(indicator, now=now)
            if not matches:
                results.append(
                    ThreatLookupResult(
                        indicator=indicator,
                        outcome=ThreatLookupOutcome.NO_MATCH,
                        snapshot_id=snapshot.snapshot_id,
                        snapshot_version=snapshot.version,
                        matches=(),
                        reason_code="no_active_match",
                    )
                )
                continue
            results.append(
                ThreatLookupResult(
                    indicator=indicator,
                    outcome=ThreatLookupOutcome.MATCH,
                    snapshot_id=snapshot.snapshot_id,
                    snapshot_version=snapshot.version,
                    matches=tuple(
                        ThreatMatch(
                            source=record.source,
                            source_record_id=record.source_record_id,
                            status=record.status,
                            expires_at=record.expires_at,
                            evidence_ref=record.evidence_ref,
                            verification_source=record.verification_source,
                        )
                        for record in matches
                    ),
                    reason_code="active_exact_match",
                )
            )
        return tuple(results)


def _unavailable(
    indicator: ThreatIndicator,
    reason_code: str,
    *,
    snapshot_id: EntityId | None,
    version: str | None,
) -> ThreatLookupResult:
    return ThreatLookupResult(
        indicator=indicator,
        outcome=ThreatLookupOutcome.UNAVAILABLE,
        snapshot_id=snapshot_id,
        snapshot_version=version,
        matches=(),
        reason_code=reason_code,
    )
