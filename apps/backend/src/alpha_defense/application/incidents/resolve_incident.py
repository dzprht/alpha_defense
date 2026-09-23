"""Record a user resolution without changing payment or freshness gates."""

from __future__ import annotations

from alpha_defense.application.incidents.dto import IncidentView, incident_to_view
from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    EventEnvelope,
    IdGenerator,
    IncidentUnitOfWorkFactory,
)
from alpha_defense.application.shared import (
    ActorContext,
    FieldViolation,
    ResourceNotFoundError,
    StaleRevisionError,
    ValidationError,
)
from alpha_defense.domain.incidents import IncidentResolutionCode
from alpha_defense.domain.shared import EntityId


class ResolveIncident:
    def __init__(
        self,
        *,
        unit_of_work: IncidentUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_generator = id_generator

    def execute(
        self,
        *,
        actor: ActorContext,
        incident_id: EntityId,
        resolution: IncidentResolutionCode,
        expected_revision: int,
    ) -> IncidentView:
        with self._unit_of_work() as uow:
            incident = uow.incidents.get(incident_id)
            if incident is None or (
                incident.owner_id != actor.user_id or incident.namespace_id != actor.namespace_id
            ):
                raise ResourceNotFoundError("Инцидент не найден.")
            if incident.revision != expected_revision:
                raise StaleRevisionError("Версия инцидента устарела.")
            resolved_at = self._clock.now_utc()
            try:
                resolved = incident.resolve(
                    code=resolution,
                    resolved_at=resolved_at,
                    resolved_by=actor.user_id,
                )
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "Инцидент нельзя перевести в указанное состояние.",
                    field_errors=(
                        FieldViolation(
                            field="resolution_code",
                            code="invalid_incident_state",
                            message="Обновите инцидент и повторите действие.",
                        ),
                    ),
                ) from exc
            uow.incidents.save(resolved, expected_revision=expected_revision)
            uow.audit.append(
                AuditRecord(
                    event=EventEnvelope(
                        event_id=self._id_generator.new_id(),
                        event_type="incident.resolved",
                        aggregate_id=incident_id,
                        aggregate_revision=resolved.revision,
                        occurred_at=resolved_at,
                        correlation_id=incident_id,
                        execution_mode=actor.execution_mode,
                        payload={
                            "resolution_code": resolution.value,
                            "context_version": resolved.context_version,
                        },
                    ),
                    actor_id=actor.user_id,
                    session_id=actor.session_id,
                    namespace_id=actor.namespace_id,
                    recorded_at=resolved_at,
                )
            )
            uow.commit()
        return incident_to_view(resolved)
