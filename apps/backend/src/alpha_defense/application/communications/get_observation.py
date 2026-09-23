"""Owner-scoped retrieval of immutable observations and raw content."""

from __future__ import annotations

from alpha_defense.application.communications.dto import ObservationView
from alpha_defense.application.communications.ingest_observation import to_view
from alpha_defense.application.ports import CommunicationsUnitOfWorkFactory
from alpha_defense.application.shared import ActorContext, ResourceNotFoundError
from alpha_defense.domain.shared import EntityId


class GetObservation:
    def __init__(self, *, unit_of_work: CommunicationsUnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, *, actor: ActorContext, observation_id: EntityId) -> ObservationView:
        with self._unit_of_work() as uow:
            stored = uow.observations.get(observation_id)
        if stored is None or (
            stored.observation.owner_id != actor.user_id
            or stored.observation.namespace_id != actor.namespace_id
        ):
            raise ResourceNotFoundError("Наблюдение не найдено.")
        return to_view(stored)
