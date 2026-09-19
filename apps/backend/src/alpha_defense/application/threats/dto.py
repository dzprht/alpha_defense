"""Transport-neutral read models for the threat registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import ThreatIndicator, ThreatRecordStatus


class ThreatLookupOutcome(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"


class RegistryAvailability(StrEnum):
    READY = "ready"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ThreatMatch:
    source: str
    source_record_id: str
    status: ThreatRecordStatus
    expires_at: datetime
    evidence_ref: str
    verification_source: str


@dataclass(frozen=True, slots=True)
class ThreatLookupResult:
    indicator: ThreatIndicator
    outcome: ThreatLookupOutcome
    snapshot_id: EntityId | None
    snapshot_version: str | None
    matches: tuple[ThreatMatch, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class RegistryStatusView:
    availability: RegistryAvailability
    snapshot_id: EntityId | None
    snapshot_version: str | None
    source_versions: tuple[str, ...]
    published_at: datetime | None
    valid_until: datetime | None
    record_count: int


@dataclass(frozen=True, slots=True)
class RefreshRegistryResult:
    snapshot_id: EntityId
    snapshot_version: str
    source_versions: tuple[str, ...]
    record_count: int
    content_sha256: str
    published: bool
