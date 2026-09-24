"""Atomic intake portion of the future analyze-contact workflow."""

from __future__ import annotations

from alpha_defense.application.communications import (
    IngestObservation,
    ObservationInput,
    ObservationView,
)
from alpha_defense.application.communications.mapping import canonical_sha256, payload_to_data
from alpha_defense.application.incidents import (
    AttachObservation,
    CorrelationKey,
    CorrelationKeyKind,
)
from alpha_defense.application.ports import (
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    IdGenerator,
    IncidentUnitOfWorkFactory,
)
from alpha_defense.application.shared import ActorContext, ServiceUnavailableError
from alpha_defense.application.workflows.dto import AnalyzeContactReceipt
from alpha_defense.domain.communications import (
    CallTranscriptPayload,
    MessengerPayload,
    NormalizationStatus,
    SmsPayload,
)


class AnalyzeContact:
    """Persist evidence, preliminary incident, and risk invalidation in one commit."""

    def __init__(
        self,
        *,
        unit_of_work: IncidentUnitOfWorkFactory,
        ingest_observation: IngestObservation,
        attach_observation: AttachObservation,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._ingest_observation = ingest_observation
        self._attach_observation = attach_observation
        self._id_generator = id_generator

    def execute(
        self,
        *,
        actor: ActorContext,
        source: str,
        observation_input: ObservationInput,
        idempotency_key: str | None = None,
    ) -> AnalyzeContactReceipt:
        with self._unit_of_work() as uow:
            intake = self._ingest_observation.execute_in_unit_of_work(
                uow=uow,
                actor=actor,
                source=source,
                observation_input=observation_input,
            )
            reservation = None
            if idempotency_key is not None:
                if self._id_generator is None:
                    raise RuntimeError("idempotency requires an id generator")
                command_hash = canonical_sha256(
                    {
                        "source": source,
                        "source_event_id": observation_input.source_event_id,
                        "occurred_at": observation_input.occurred_at.isoformat(),
                        "payload": payload_to_data(observation_input.payload),
                    }
                )
                reservation = uow.idempotency.reserve(
                    IdempotencyRecord(
                        record_id=self._id_generator.new_id(),
                        scope=IdempotencyScope(
                            principal_fingerprint=canonical_sha256(
                                {"actor_id": str(actor.user_id)}
                            ),
                            session_id=actor.session_id,
                            namespace_id=actor.namespace_id,
                            method="POST",
                            canonical_route="/api/v1/observations",
                            key=idempotency_key,
                        ),
                        command_hash=command_hash,
                        resource_id=intake.observation.observation_id,
                        state=IdempotencyState.IN_PROGRESS,
                        result=None,
                        revision=0,
                        created_at=intake.observation.received_at,
                        updated_at=intake.observation.received_at,
                    )
                )
                if (
                    not reservation.is_new
                    and reservation.record.state is not IdempotencyState.COMPLETED
                ):
                    raise ServiceUnavailableError("Contact intake replay is incomplete")
            attachment = self._attach_observation.execute_in_unit_of_work(
                uow=uow,
                actor=actor,
                observation_id=intake.observation.observation_id,
                available_keys=_correlation_keys(intake.observation),
                accepted_at=intake.observation.received_at,
            )
            if reservation is not None and reservation.is_new:
                uow.idempotency.save(
                    reservation.record.finish(
                        state=IdempotencyState.COMPLETED,
                        result={
                            "observation_id": str(intake.observation.observation_id),
                            "incident_id": str(attachment.incident.incident_id),
                        },
                        updated_at=intake.observation.received_at,
                    ),
                    expected_revision=0,
                )
            uow.commit()
        return AnalyzeContactReceipt(
            observation=intake.observation,
            incident=attachment.incident,
            risk_state=attachment.risk_state,
            duplicate_source_event=intake.duplicate,
            created_incident=attachment.created_incident,
        )


def _correlation_keys(observation: ObservationView) -> tuple[CorrelationKey, ...]:
    keys: list[CorrelationKey] = []
    payload = observation.payload
    if isinstance(payload, (SmsPayload, MessengerPayload)):
        keys.append(
            CorrelationKey(
                kind=CorrelationKeyKind.CONVERSATION,
                value=payload.conversation_id,
            )
        )
    elif isinstance(payload, CallTranscriptPayload):
        keys.append(CorrelationKey(kind=CorrelationKeyKind.CALL, value=payload.call_id))
    for indicator in observation.normalized_indicators:
        if (
            indicator.status is NormalizationStatus.NORMALIZED
            and indicator.normalized_value is not None
        ):
            keys.append(
                CorrelationKey(
                    kind=CorrelationKeyKind.INDICATOR,
                    value=f"{indicator.indicator_type.value}:{indicator.normalized_value}",
                )
            )
    return tuple(sorted(set(keys)))
