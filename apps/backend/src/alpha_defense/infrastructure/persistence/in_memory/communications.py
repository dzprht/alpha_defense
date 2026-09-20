"""In-memory persistence for immutable observations and separately stored content."""

from __future__ import annotations

from alpha_defense.application.communications.mapping import canonical_sha256, payload_to_data
from alpha_defense.application.shared import ServiceUnavailableError
from alpha_defense.domain.communications import StoredObservation
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryState


class InMemoryObservationRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get(self, observation_id: EntityId) -> StoredObservation | None:
        observation = self._state.observations.get(observation_id)
        if observation is None:
            return None
        content = self._state.observation_contents.get(observation.content_ref)
        if content is None:
            raise ServiceUnavailableError("Persisted observation content is incomplete")
        if canonical_sha256(payload_to_data(content.payload)) != content.content_sha256:
            raise ServiceUnavailableError("Persisted observation content is invalid")
        return StoredObservation(observation=observation, content=content)

    def get_by_source_event(
        self,
        *,
        namespace_id: EntityId,
        source: str,
        source_event_id: str,
    ) -> StoredObservation | None:
        observation_id = self._state.observation_source_events.get(
            (namespace_id, source, source_event_id)
        )
        return None if observation_id is None else self.get(observation_id)

    def add(self, stored: StoredObservation) -> None:
        observation = stored.observation
        source_key = (observation.namespace_id, observation.source, observation.source_event_id)
        existing = self.get(observation.observation_id)
        existing_source_id = self._state.observation_source_events.get(source_key)
        if existing == stored and existing_source_id == observation.observation_id:
            return
        if (
            existing is not None
            or existing_source_id is not None
            or observation.content_ref in self._state.observation_contents
        ):
            raise ValueError("observation id, content ref, or source event already exists")
        self._state.observations[observation.observation_id] = observation
        self._state.observation_contents[observation.content_ref] = stored.content
        self._state.observation_source_events[source_key] = observation.observation_id
