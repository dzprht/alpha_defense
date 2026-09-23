"""Persistence contracts for incidents and namespace risk freshness."""

from __future__ import annotations

from typing import Protocol

from alpha_defense.application.ports.communications import CommunicationsUnitOfWorkPort
from alpha_defense.domain.incidents import Incident, NamespaceRiskState
from alpha_defense.domain.shared import EntityId


class IncidentRepositoryPort(Protocol):
    def get(self, incident_id: EntityId) -> Incident | None: ...

    def get_by_observation(self, observation_id: EntityId) -> Incident | None: ...

    def list_for_scope(
        self,
        *,
        owner_id: EntityId,
        namespace_id: EntityId,
    ) -> tuple[Incident, ...]: ...

    def add(self, incident: Incident) -> None: ...

    def save(self, incident: Incident, *, expected_revision: int) -> None: ...


class NamespaceRiskStateRepositoryPort(Protocol):
    def get(self, namespace_id: EntityId) -> NamespaceRiskState | None: ...

    def add(self, state: NamespaceRiskState) -> None: ...

    def save(self, state: NamespaceRiskState, *, expected_revision: int) -> None: ...


class IncidentUnitOfWorkPort(CommunicationsUnitOfWorkPort, Protocol):
    @property
    def incidents(self) -> IncidentRepositoryPort: ...

    @property
    def namespace_risk_states(self) -> NamespaceRiskStateRepositoryPort: ...


class IncidentUnitOfWorkFactory(Protocol):
    def __call__(self) -> IncidentUnitOfWorkPort: ...
