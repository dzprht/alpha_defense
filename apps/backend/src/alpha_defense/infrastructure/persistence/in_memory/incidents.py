"""In-memory incident aggregates and namespace risk freshness."""

from __future__ import annotations

from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.domain.incidents import Incident, NamespaceRiskState
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryState


class InMemoryIncidentRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get(self, incident_id: EntityId) -> Incident | None:
        return self._state.incidents.get(incident_id)

    def get_by_observation(self, observation_id: EntityId) -> Incident | None:
        incident_id = self._state.incidents_by_observation.get(observation_id)
        return None if incident_id is None else self.get(incident_id)

    def list_for_scope(
        self,
        *,
        owner_id: EntityId,
        namespace_id: EntityId,
    ) -> tuple[Incident, ...]:
        return tuple(
            sorted(
                (
                    incident
                    for incident in self._state.incidents.values()
                    if incident.owner_id == owner_id and incident.namespace_id == namespace_id
                ),
                key=lambda incident: (incident.updated_at, str(incident.incident_id)),
            )
        )

    def add(self, incident: Incident) -> None:
        existing = self._state.incidents.get(incident.incident_id)
        if existing == incident:
            return
        if existing is not None:
            raise ValueError("incident_id already exists")
        self._validate_new_observations(incident)
        self._state.incidents[incident.incident_id] = incident
        for observation_id in incident.observation_ids:
            self._state.incidents_by_observation[observation_id] = incident.incident_id

    def save(self, incident: Incident, *, expected_revision: int) -> None:
        current = self._state.incidents.get(incident.incident_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Incident revision is stale")
        if incident.revision != expected_revision + 1:
            raise StaleRevisionError("Incident revision must advance by one")
        _assert_incident_update(current, incident)
        self._validate_new_observations(incident)
        self._state.incidents[incident.incident_id] = incident
        for observation_id in incident.observation_ids:
            self._state.incidents_by_observation[observation_id] = incident.incident_id

    def _validate_new_observations(self, incident: Incident) -> None:
        for observation_id in incident.observation_ids:
            if observation_id not in self._state.observations:
                raise ValueError("incident observation does not exist")
            mapped = self._state.incidents_by_observation.get(observation_id)
            if mapped is not None and mapped != incident.incident_id:
                raise ValueError("observation is already attached to another incident")


class InMemoryNamespaceRiskStateRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get(self, namespace_id: EntityId) -> NamespaceRiskState | None:
        return self._state.namespace_risk_states.get(namespace_id)

    def add(self, state: NamespaceRiskState) -> None:
        existing = self.get(state.namespace_id)
        if existing == state:
            return
        if existing is not None:
            raise ValueError("namespace risk state already exists")
        self._validate_references(state)
        self._state.namespace_risk_states[state.namespace_id] = state

    def save(self, state: NamespaceRiskState, *, expected_revision: int) -> None:
        current = self.get(state.namespace_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Namespace risk state revision is stale")
        if state.revision != expected_revision + 1:
            raise StaleRevisionError("Namespace risk state revision must advance by one")
        if (
            current.owner_id != state.owner_id
            or current.session_id != state.session_id
            or current.execution_mode is not state.execution_mode
            or state.ingress_risk_epoch < current.ingress_risk_epoch
        ):
            raise ValueError("immutable namespace risk state fields cannot be changed")
        self._validate_references(state)
        self._state.namespace_risk_states[state.namespace_id] = state

    def _validate_references(self, state: NamespaceRiskState) -> None:
        for pending in state.pending_analyses:
            incident = self._state.incidents.get(pending.incident_id)
            if (
                pending.observation_id not in self._state.observations
                or incident is None
                or pending.observation_id not in incident.observation_ids
                or incident.owner_id != state.owner_id
                or incident.namespace_id != state.namespace_id
            ):
                raise ValueError("pending analysis references an inconsistent incident")


def _assert_incident_update(current: Incident, updated: Incident) -> None:
    if (
        current.owner_id != updated.owner_id
        or current.session_id != updated.session_id
        or current.namespace_id != updated.namespace_id
        or current.created_at != updated.created_at
        or current.execution_mode is not updated.execution_mode
    ):
        raise ValueError("immutable incident fields cannot be changed")
    if (
        updated.observation_links[: len(current.observation_links)] != current.observation_links
        or updated.assessment_links[: len(current.assessment_links)] != current.assessment_links
        or updated.resolution_history[: len(current.resolution_history)]
        != current.resolution_history
    ):
        raise ValueError("incident timeline history is append-only")
