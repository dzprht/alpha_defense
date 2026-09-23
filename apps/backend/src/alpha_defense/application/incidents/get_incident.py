"""Owner-scoped incident and timeline retrieval."""

from __future__ import annotations

from alpha_defense.application.incidents.dto import IncidentView, incident_to_view
from alpha_defense.application.ports import IncidentUnitOfWorkFactory
from alpha_defense.application.shared import ActorContext, ResourceNotFoundError
from alpha_defense.domain.shared import EntityId


class GetIncident:
    def __init__(self, *, unit_of_work: IncidentUnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def execute(self, *, actor: ActorContext, incident_id: EntityId) -> IncidentView:
        with self._unit_of_work() as uow:
            incident = uow.incidents.get(incident_id)
        if incident is None or (
            incident.owner_id != actor.user_id or incident.namespace_id != actor.namespace_id
        ):
            raise ResourceNotFoundError("Инцидент не найден.")
        return incident_to_view(incident)
