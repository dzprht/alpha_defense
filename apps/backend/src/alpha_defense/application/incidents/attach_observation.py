"""Attach one persisted observation and invalidate namespace risk context."""

from __future__ import annotations

from datetime import datetime

from alpha_defense.application.incidents.dto import (
    AttachObservationResult,
    incident_to_view,
    risk_state_to_view,
)
from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    EventEnvelope,
    IdGenerator,
    IncidentUnitOfWorkFactory,
    IncidentUnitOfWorkPort,
)
from alpha_defense.application.shared import ActorContext, ResourceNotFoundError
from alpha_defense.domain.incidents import (
    CorrelationKey,
    Incident,
    NamespaceRiskState,
    PreliminaryCorrelationPolicy,
)
from alpha_defense.domain.shared import EntityId


class AttachObservation:
    def __init__(
        self,
        *,
        unit_of_work: IncidentUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
        correlation_policy: PreliminaryCorrelationPolicy | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_generator = id_generator
        self._correlation_policy = correlation_policy or PreliminaryCorrelationPolicy()

    def execute(
        self,
        *,
        actor: ActorContext,
        observation_id: EntityId,
        available_keys: tuple[CorrelationKey, ...],
    ) -> AttachObservationResult:
        with self._unit_of_work() as uow:
            result = self.execute_in_unit_of_work(
                uow=uow,
                actor=actor,
                observation_id=observation_id,
                available_keys=available_keys,
                accepted_at=self._clock.now_utc(),
            )
            uow.commit()
        return result

    def execute_in_unit_of_work(
        self,
        *,
        uow: IncidentUnitOfWorkPort,
        actor: ActorContext,
        observation_id: EntityId,
        available_keys: tuple[CorrelationKey, ...],
        accepted_at: datetime,
    ) -> AttachObservationResult:
        available_keys = tuple(sorted(set(available_keys)))
        stored = uow.observations.get(observation_id)
        if stored is None or (
            stored.observation.owner_id != actor.user_id
            or stored.observation.namespace_id != actor.namespace_id
        ):
            raise ResourceNotFoundError("Наблюдение не найдено.")
        existing_incident = uow.incidents.get_by_observation(observation_id)
        if existing_incident is not None:
            state = _require_risk_state(uow, actor=actor)
            return AttachObservationResult(
                incident=incident_to_view(existing_incident),
                risk_state=risk_state_to_view(state),
                created_incident=False,
            )

        candidates = uow.incidents.list_for_scope(
            owner_id=actor.user_id,
            namespace_id=actor.namespace_id,
        )
        match = self._correlation_policy.choose(
            candidates=candidates,
            available_keys=available_keys,
        )
        created_incident = match is None
        if match is None:
            incident = Incident.create(
                incident_id=self._id_generator.new_id(),
                owner_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                observation_id=observation_id,
                available_keys=available_keys,
                created_at=accepted_at,
                execution_mode=actor.execution_mode,
            )
            uow.incidents.add(incident)
        else:
            matched = next(item for item in candidates if item.incident_id == match.incident_id)
            incident = matched.attach_observation(
                observation_id=observation_id,
                available_keys=available_keys,
                correlation_reason=match.reason,
                correlation_key=match.key,
                attached_at=accepted_at,
            )
            uow.incidents.save(incident, expected_revision=matched.revision)

        current_state = uow.namespace_risk_states.get(actor.namespace_id)
        if current_state is None:
            risk_state = NamespaceRiskState.create(
                namespace_id=actor.namespace_id,
                owner_id=actor.user_id,
                session_id=actor.session_id,
                observation_id=observation_id,
                incident_id=incident.incident_id,
                accepted_at=accepted_at,
                execution_mode=actor.execution_mode,
            )
            uow.namespace_risk_states.add(risk_state)
        else:
            _require_actor_scope(current_state, actor)
            risk_state = current_state.accept(
                observation_id=observation_id,
                incident_id=incident.incident_id,
                accepted_at=accepted_at,
            )
            uow.namespace_risk_states.save(
                risk_state,
                expected_revision=current_state.revision,
            )

        uow.audit.append(
            AuditRecord(
                event=EventEnvelope(
                    event_id=self._id_generator.new_id(),
                    event_type="incident.observation_attached",
                    aggregate_id=incident.incident_id,
                    aggregate_revision=incident.revision,
                    occurred_at=accepted_at,
                    correlation_id=incident.incident_id,
                    execution_mode=actor.execution_mode,
                    payload={
                        "observation_id": str(observation_id),
                        "context_version": incident.context_version,
                        "ingress_risk_epoch": risk_state.ingress_risk_epoch,
                        "analysis_pending": True,
                    },
                ),
                actor_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                recorded_at=accepted_at,
            )
        )
        return AttachObservationResult(
            incident=incident_to_view(incident),
            risk_state=risk_state_to_view(risk_state),
            created_incident=created_incident,
        )


def _require_actor_scope(state: NamespaceRiskState, actor: ActorContext) -> None:
    if (
        state.owner_id != actor.user_id
        or state.namespace_id != actor.namespace_id
        or state.execution_mode is not actor.execution_mode
    ):
        raise ValueError("namespace risk state ownership is inconsistent")


def _require_risk_state(
    uow: IncidentUnitOfWorkPort,
    *,
    actor: ActorContext,
) -> NamespaceRiskState:
    state = uow.namespace_risk_states.get(actor.namespace_id)
    if state is None:
        raise ValueError("attached observation has no namespace risk state")
    _require_actor_scope(state, actor)
    return state
