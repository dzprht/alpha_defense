"""Atomic in-memory threat snapshot publication."""

from __future__ import annotations

from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import RegistrySnapshot
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryState


class InMemoryThreatRegistryRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get_current(self) -> RegistrySnapshot | None:
        snapshot_id = self._state.current_threat_snapshot_id
        return None if snapshot_id is None else self._state.threat_snapshots[snapshot_id]

    def get_by_version(self, version: str) -> RegistrySnapshot | None:
        snapshot_id = self._state.threat_snapshot_versions.get(version)
        return None if snapshot_id is None else self._state.threat_snapshots[snapshot_id]

    def publish(
        self,
        snapshot: RegistrySnapshot,
        *,
        expected_current_id: EntityId | None,
    ) -> RegistrySnapshot:
        existing = self.get_by_version(snapshot.version)
        if existing is not None:
            if not existing.has_same_content(snapshot):
                raise ValueError("registry version already exists with different content")
            return existing
        if self._state.current_threat_snapshot_id != expected_current_id:
            raise StaleRevisionError("current threat snapshot changed concurrently")
        if snapshot.snapshot_id in self._state.threat_snapshots:
            raise ValueError("snapshot_id already exists")
        self._state.threat_snapshots[snapshot.snapshot_id] = snapshot
        self._state.threat_snapshot_versions[snapshot.version] = snapshot.snapshot_id
        self._state.current_threat_snapshot_id = snapshot.snapshot_id
        return snapshot

    def list_versions(self) -> tuple[str, ...]:
        return tuple(sorted(self._state.threat_snapshot_versions))
