"""Ports for untrusted threat feeds and atomic registry persistence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from alpha_defense.application.ports.unit_of_work import UnitOfWorkPort
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import RegistrySnapshot


@dataclass(frozen=True, slots=True)
class ThreatFeedRecord:
    source_record_id: str
    indicator_type: str
    value: str
    normalization_version: str
    status: str
    first_seen_at: datetime
    observed_at: datetime
    expires_at: datetime
    evidence_ref: str
    verification_source: str


@dataclass(frozen=True, slots=True)
class ThreatBatch:
    source: str
    source_version: str
    generated_at: datetime
    valid_until: datetime
    records: tuple[ThreatFeedRecord, ...]


class ThreatFeedUnavailableError(RuntimeError):
    """The feed could not provide a complete validated batch."""


class ThreatFeedPort(Protocol):
    def fetch(self, source: str) -> ThreatBatch: ...


class ThreatRegistryRepositoryPort(Protocol):
    def get_current(self) -> RegistrySnapshot | None: ...

    def get_by_version(self, version: str) -> RegistrySnapshot | None: ...

    def publish(
        self,
        snapshot: RegistrySnapshot,
        *,
        expected_current_id: EntityId | None,
    ) -> RegistrySnapshot: ...

    def list_versions(self) -> Sequence[str]: ...


class ThreatUnitOfWorkPort(UnitOfWorkPort, Protocol):
    @property
    def threat_registry(self) -> ThreatRegistryRepositoryPort: ...


class ThreatUnitOfWorkFactory(Protocol):
    def __call__(self) -> ThreatUnitOfWorkPort: ...
