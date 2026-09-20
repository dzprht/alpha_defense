"""Validate, normalize, deduplicate, and persist one immutable observation."""

# ruff: noqa: RUF001

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from alpha_defense.application.communications.dto import (
    IngestObservationResult,
    ObservationInput,
    ObservationView,
)
from alpha_defense.application.communications.mapping import canonical_sha256, payload_to_data
from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    CommunicationsUnitOfWorkFactory,
    CommunicationsUnitOfWorkPort,
    EventEnvelope,
    IdGenerator,
)
from alpha_defense.application.shared import ActorContext, FieldViolation, ValidationError
from alpha_defense.domain.communications import (
    CallTranscriptPayload,
    CommunicationIndicatorType,
    IndicatorOrigin,
    MessengerPayload,
    NormalizationStatus,
    NormalizedIndicator,
    Observation,
    ObservationContent,
    SmsPayload,
    StoredObservation,
    WebResourcePayload,
    indicators_from_resource,
    indicators_from_text,
)
from alpha_defense.domain.shared import EntityId

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SOURCE = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")


class IngestObservation:
    def __init__(
        self,
        *,
        unit_of_work: CommunicationsUnitOfWorkFactory,
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
        source: str,
        observation_input: ObservationInput,
    ) -> IngestObservationResult:
        with self._unit_of_work() as uow:
            result = self.execute_in_unit_of_work(
                uow=uow,
                actor=actor,
                source=source,
                observation_input=observation_input,
            )
            uow.commit()
        return result

    def execute_in_unit_of_work(
        self,
        *,
        uow: CommunicationsUnitOfWorkPort,
        actor: ActorContext,
        source: str,
        observation_input: ObservationInput,
    ) -> IngestObservationResult:
        """Apply intake without committing so a coordinating workflow can stay atomic."""

        received_at = self._clock.now_utc()
        try:
            _validate_input_metadata(
                source=source,
                source_event_id=observation_input.source_event_id,
                occurred_at=observation_input.occurred_at,
            )
            raw_payload = payload_to_data(observation_input.payload)
            source_event_fingerprint = canonical_sha256(
                {
                    "kind": observation_input.payload.kind.value,
                    "source_event_id": observation_input.source_event_id,
                    "occurred_at": _timestamp(observation_input.occurred_at),
                    "payload": raw_payload,
                }
            )
            content_sha256 = canonical_sha256(raw_payload)
            indicators = _normalize_payload(observation_input.payload)
            if isinstance(observation_input.payload, WebResourcePayload):
                invalid_url = next(
                    (
                        item
                        for item in indicators
                        if item.indicator_type is CommunicationIndicatorType.URL
                        and item.status is NormalizationStatus.INVALID
                    ),
                    None,
                )
                if invalid_url is not None:
                    raise ValidationError(
                        "URL ресурса имеет неподдерживаемый формат.",
                        field_errors=(
                            FieldViolation(
                                field="payload.url",
                                code="invalid_url",
                                message="Укажите полный URL с http или https.",
                            ),
                        ),
                    )
        except ValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ValidationError("Наблюдение не прошло проверку.") from exc

        if observation_input.occurred_at > received_at + timedelta(minutes=5):
            raise ValidationError(
                "Время наблюдения слишком далеко в будущем.",
                field_errors=(
                    FieldViolation(
                        field="occurred_at",
                        code="future_timestamp",
                        message="Время не может опережать сервер более чем на пять минут.",
                    ),
                ),
            )

        existing = uow.observations.get_by_source_event(
            namespace_id=actor.namespace_id,
            source=source,
            source_event_id=observation_input.source_event_id,
        )
        if existing is not None:
            if existing.observation.source_event_fingerprint != source_event_fingerprint:
                raise ValidationError(
                    "Идентификатор события уже использован для другого содержимого.",
                    field_errors=(
                        FieldViolation(
                            field="source_event_id",
                            code="source_event_conflict",
                            message="Повторите исходное событие без изменения данных.",
                        ),
                    ),
                )
            return IngestObservationResult(
                observation=_view(existing),
                duplicate=True,
            )

        observation_id = self._id_generator.new_id()
        content_ref = self._id_generator.new_id()
        correlation = _correlation_fields(observation_input.payload)
        media_refs = _media_refs(observation_input.payload)
        observation = Observation(
            observation_id=observation_id,
            owner_id=actor.user_id,
            session_id=actor.session_id,
            namespace_id=actor.namespace_id,
            kind=observation_input.payload.kind,
            source=source,
            source_event_id=observation_input.source_event_id,
            source_event_fingerprint=source_event_fingerprint,
            occurred_at=observation_input.occurred_at,
            received_at=received_at,
            content_ref=content_ref,
            normalized_indicators=indicators,
            media_refs=media_refs,
            execution_mode=actor.execution_mode,
            conversation_id=correlation[0],
            call_id=correlation[1],
            sequence=correlation[2],
        )
        content = ObservationContent(
            content_ref=content_ref,
            observation_id=observation_id,
            payload=observation_input.payload,
            content_sha256=content_sha256,
        )
        stored = StoredObservation(observation=observation, content=content)
        uow.observations.add(stored)
        uow.audit.append(
            AuditRecord(
                event=EventEnvelope(
                    event_id=self._id_generator.new_id(),
                    event_type="observation.received",
                    aggregate_id=observation_id,
                    aggregate_revision=0,
                    occurred_at=received_at,
                    correlation_id=observation_id,
                    execution_mode=actor.execution_mode,
                    payload={
                        "kind": observation.kind.value,
                        "source": observation.source,
                        "normalization_version": observation.normalization_version,
                        "indicator_count": len(observation.normalized_indicators),
                    },
                ),
                actor_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                recorded_at=received_at,
            )
        )
        return IngestObservationResult(observation=_view(stored), duplicate=False)


def _normalize_payload(payload: object) -> tuple[NormalizedIndicator, ...]:
    if isinstance(payload, (SmsPayload, MessengerPayload)):
        return indicators_from_text(payload.text, sender=payload.sender)
    if isinstance(payload, CallTranscriptPayload):
        return indicators_from_text(
            payload.transcript,
            sender=payload.phone,
            sender_origin=IndicatorOrigin.CALLER,
        )
    if isinstance(payload, WebResourcePayload):
        return () if payload.url is None else indicators_from_resource(payload.url)
    raise TypeError("unsupported observation payload")


def _validate_input_metadata(
    *,
    source: str,
    source_event_id: str,
    occurred_at: datetime,
) -> None:
    violations: list[FieldViolation] = []
    if not isinstance(source, str) or not _SOURCE.fullmatch(source):
        violations.append(
            FieldViolation(
                field="source",
                code="invalid_source",
                message="Источник должен быть назначен доверенным адаптером.",
            )
        )
    if not isinstance(source_event_id, str) or not _STABLE_ID.fullmatch(source_event_id):
        violations.append(
            FieldViolation(
                field="source_event_id",
                code="invalid_source_event_id",
                message="Идентификатор события имеет неверный формат.",
            )
        )
    if (
        not isinstance(occurred_at, datetime)
        or occurred_at.tzinfo is None
        or occurred_at.utcoffset() != UTC.utcoffset(occurred_at)
    ):
        violations.append(
            FieldViolation(
                field="occurred_at",
                code="invalid_timestamp",
                message="Укажите время UTC с часовым поясом.",
            )
        )
    if violations:
        raise ValidationError("Метаданные наблюдения не прошли проверку.", field_errors=violations)


def _correlation_fields(payload: object) -> tuple[str | None, str | None, int | None]:
    if isinstance(payload, (SmsPayload, MessengerPayload)):
        return (payload.conversation_id, None, None)
    if isinstance(payload, CallTranscriptPayload):
        return (None, payload.call_id, payload.sequence)
    if isinstance(payload, WebResourcePayload):
        return (None, None, None)
    raise TypeError("unsupported observation payload")


def _media_refs(payload: object) -> tuple[EntityId, ...]:
    if isinstance(payload, WebResourcePayload) and payload.media_id is not None:
        return (payload.media_id,)
    return ()


def _timestamp(value: datetime) -> str:
    rendered = value.isoformat()
    return rendered.replace("+00:00", "Z")


def _view(stored: StoredObservation) -> ObservationView:
    observation = stored.observation
    return ObservationView(
        observation_id=observation.observation_id,
        owner_id=observation.owner_id,
        session_id=observation.session_id,
        namespace_id=observation.namespace_id,
        kind=observation.kind,
        source=observation.source,
        source_event_id=observation.source_event_id,
        occurred_at=observation.occurred_at,
        received_at=observation.received_at,
        payload=stored.content.payload,
        normalized_indicators=observation.normalized_indicators,
        media_refs=observation.media_refs,
        normalization_version=observation.normalization_version,
        execution_mode=observation.execution_mode,
    )


to_view = _view
