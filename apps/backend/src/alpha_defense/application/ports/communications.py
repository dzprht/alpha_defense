"""Persistence contracts for immutable communication observations."""

from __future__ import annotations

from typing import Protocol

from alpha_defense.application.ports.unit_of_work import UnitOfWorkPort
from alpha_defense.domain.communications import StoredObservation
from alpha_defense.domain.shared import EntityId


class ObservationRepositoryPort(Protocol):
    def get(self, observation_id: EntityId) -> StoredObservation | None: ...

    def get_by_source_event(
        self,
        *,
        namespace_id: EntityId,
        source: str,
        source_event_id: str,
    ) -> StoredObservation | None: ...

    def add(self, stored: StoredObservation) -> None: ...


class CommunicationsUnitOfWorkPort(UnitOfWorkPort, Protocol):
    @property
    def observations(self) -> ObservationRepositoryPort: ...


class CommunicationsUnitOfWorkFactory(Protocol):
    def __call__(self) -> CommunicationsUnitOfWorkPort: ...
