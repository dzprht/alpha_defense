"""Atomic intake portion of the future analyze-contact workflow."""

from __future__ import annotations

from alpha_defense.application.communications import (
    IngestObservation,
    ObservationInput,
    ObservationView,
)
from alpha_defense.application.incidents import (
    AttachObservation,
    CorrelationKey,
    CorrelationKeyKind,
)
from alpha_defense.application.ports import IncidentUnitOfWorkFactory
from alpha_defense.application.shared import ActorContext
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
    ) -> None:
        self._unit_of_work = unit_of_work
        self._ingest_observation = ingest_observation
        self._attach_observation = attach_observation

    def execute(
        self,
        *,
        actor: ActorContext,
        source: str,
        observation_input: ObservationInput,
    ) -> AnalyzeContactReceipt:
        with self._unit_of_work() as uow:
            intake = self._ingest_observation.execute_in_unit_of_work(
                uow=uow,
                actor=actor,
                source=source,
                observation_input=observation_input,
            )
            attachment = self._attach_observation.execute_in_unit_of_work(
                uow=uow,
                actor=actor,
                observation_id=intake.observation.observation_id,
                available_keys=_correlation_keys(intake.observation),
                accepted_at=intake.observation.received_at,
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
