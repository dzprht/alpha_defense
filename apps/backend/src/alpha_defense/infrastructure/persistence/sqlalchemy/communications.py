"""SQLite persistence for immutable observation metadata, content, and indicators."""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Result, RowMapping
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.communications.mapping import canonical_sha256, payload_to_data
from alpha_defense.application.shared import ServiceUnavailableError
from alpha_defense.domain.communications import (
    CallTranscriptPayload,
    CommunicationIndicatorType,
    IndicatorOrigin,
    MessengerPayload,
    NormalizationStatus,
    NormalizedIndicator,
    Observation,
    ObservationContent,
    ObservationKind,
    ObservationPayload,
    SmsPayload,
    StoredObservation,
    TranscriptSegment,
    WebResourcePayload,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode
from alpha_defense.infrastructure.persistence.sqlalchemy.mappers import as_utc, dump_json
from alpha_defense.infrastructure.persistence.sqlalchemy.schema import (
    observation_content,
    observation_indicators,
    observations,
)


class SqlAlchemyObservationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, observation_id: EntityId) -> StoredObservation | None:
        row = (
            _execute(
                self._session,
                sa.select(observations).where(observations.c.observation_id == str(observation_id)),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._stored_from_row(row)

    def get_by_source_event(
        self,
        *,
        namespace_id: EntityId,
        source: str,
        source_event_id: str,
    ) -> StoredObservation | None:
        row = (
            _execute(
                self._session,
                sa.select(observations).where(
                    observations.c.namespace_id == str(namespace_id),
                    observations.c.source == source,
                    observations.c.source_event_id == source_event_id,
                ),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._stored_from_row(row)

    def add(self, stored: StoredObservation) -> None:
        observation = stored.observation
        _execute(self._session, sa.insert(observations).values(_observation_values(observation)))
        _execute(
            self._session,
            sa.insert(observation_content).values(
                content_ref=str(stored.content.content_ref),
                observation_id=str(stored.content.observation_id),
                payload_json=dump_json(payload_to_data(stored.content.payload)),
                content_sha256=stored.content.content_sha256,
            ),
        )
        if observation.normalized_indicators:
            _execute(
                self._session,
                sa.insert(observation_indicators).values(
                    [
                        _indicator_values(observation.observation_id, ordinal, indicator)
                        for ordinal, indicator in enumerate(observation.normalized_indicators)
                    ]
                ),
            )

    def _stored_from_row(self, row: RowMapping) -> StoredObservation:
        content_row = (
            _execute(
                self._session,
                sa.select(observation_content).where(
                    observation_content.c.observation_id == row["observation_id"]
                ),
            )
            .mappings()
            .one_or_none()
        )
        if content_row is None or content_row["content_ref"] != row["content_ref"]:
            raise ServiceUnavailableError("Persisted observation content is incomplete")
        indicator_rows = _execute(
            self._session,
            sa.select(observation_indicators)
            .where(observation_indicators.c.observation_id == row["observation_id"])
            .order_by(observation_indicators.c.ordinal),
        ).mappings()
        indicators = tuple(_indicator_from_row(item) for item in indicator_rows)
        kind = ObservationKind(row["kind"])
        payload = _payload_from_json(kind, content_row["payload_json"])
        if canonical_sha256(payload_to_data(payload)) != content_row["content_sha256"]:
            raise ServiceUnavailableError("Persisted observation content is invalid")
        observation = Observation(
            observation_id=EntityId.from_string(row["observation_id"]),
            owner_id=EntityId.from_string(row["owner_id"]),
            session_id=EntityId.from_string(row["session_id"]),
            namespace_id=EntityId.from_string(row["namespace_id"]),
            kind=kind,
            source=row["source"],
            source_event_id=row["source_event_id"],
            source_event_fingerprint=row["source_event_fingerprint"],
            occurred_at=as_utc(row["occurred_at"]),
            received_at=as_utc(row["received_at"]),
            content_ref=EntityId.from_string(row["content_ref"]),
            normalized_indicators=indicators,
            media_refs=_media_refs(row["media_refs_json"]),
            normalization_version=row["normalization_version"],
            execution_mode=ExecutionMode(row["execution_mode"]),
            conversation_id=row["conversation_id"],
            call_id=row["call_id"],
            sequence=row["sequence"],
        )
        content = ObservationContent(
            content_ref=EntityId.from_string(content_row["content_ref"]),
            observation_id=EntityId.from_string(content_row["observation_id"]),
            payload=payload,
            content_sha256=content_row["content_sha256"],
        )
        return StoredObservation(observation=observation, content=content)


def _observation_values(observation: Observation) -> dict[str, Any]:
    return {
        "observation_id": str(observation.observation_id),
        "owner_id": str(observation.owner_id),
        "session_id": str(observation.session_id),
        "namespace_id": str(observation.namespace_id),
        "kind": observation.kind.value,
        "source": observation.source,
        "source_event_id": observation.source_event_id,
        "source_event_fingerprint": observation.source_event_fingerprint,
        "occurred_at": observation.occurred_at,
        "received_at": observation.received_at,
        "content_ref": str(observation.content_ref),
        "normalization_version": observation.normalization_version,
        "execution_mode": observation.execution_mode.value,
        "conversation_id": observation.conversation_id,
        "call_id": observation.call_id,
        "sequence": observation.sequence,
        "media_refs_json": dump_json([str(item) for item in observation.media_refs]),
    }


def _indicator_values(
    observation_id: EntityId,
    ordinal: int,
    indicator: NormalizedIndicator,
) -> dict[str, Any]:
    return {
        "observation_id": str(observation_id),
        "ordinal": ordinal,
        "indicator_type": indicator.indicator_type.value,
        "origin": indicator.origin.value,
        "raw_value": indicator.raw_value,
        "normalized_value": indicator.normalized_value,
        "status": indicator.status.value,
        "normalization_version": indicator.normalization_version,
    }


def _indicator_from_row(row: RowMapping) -> NormalizedIndicator:
    return NormalizedIndicator(
        indicator_type=CommunicationIndicatorType(row["indicator_type"]),
        origin=IndicatorOrigin(row["origin"]),
        raw_value=row["raw_value"],
        normalized_value=row["normalized_value"],
        status=NormalizationStatus(row["status"]),
        normalization_version=row["normalization_version"],
    )


def _payload_from_json(kind: ObservationKind, value: str) -> ObservationPayload:
    decoded: Any = json.loads(value)
    if not isinstance(decoded, dict):
        raise ServiceUnavailableError("Persisted observation content is invalid")
    try:
        if kind is ObservationKind.SMS:
            return SmsPayload(
                text=_string(decoded, "text"),
                sender=_string(decoded, "sender"),
                conversation_id=_string(decoded, "conversation_id"),
            )
        if kind is ObservationKind.MESSENGER:
            return MessengerPayload(
                text=_string(decoded, "text"),
                sender=_string(decoded, "sender"),
                conversation_id=_string(decoded, "conversation_id"),
            )
        if kind is ObservationKind.CALL_TRANSCRIPT:
            raw_segments = decoded.get("segments")
            if not isinstance(raw_segments, list):
                raise ValueError("segments must be a list")
            segments = tuple(
                TranscriptSegment(
                    sequence=_integer(item, "sequence"),
                    text=_string(item, "text"),
                    start_ms=_optional_integer(item, "start_ms"),
                    end_ms=_optional_integer(item, "end_ms"),
                )
                for item in raw_segments
                if isinstance(item, dict)
            )
            if len(segments) != len(raw_segments):
                raise ValueError("segments must contain objects")
            return CallTranscriptPayload(
                transcript=_string(decoded, "transcript"),
                phone=_string(decoded, "phone"),
                call_id=_string(decoded, "call_id"),
                sequence=_integer(decoded, "sequence"),
                segments=segments,
            )
        return WebResourcePayload(
            url=_optional_string(decoded, "url"),
            media_id=_optional_entity_id(decoded, "media_id"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceUnavailableError("Persisted observation content is invalid") from exc


def _media_refs(value: str) -> tuple[EntityId, ...]:
    decoded: Any = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ServiceUnavailableError("Persisted media references are invalid")
    return tuple(EntityId.from_string(item) for item in decoded)


def _string(value: dict[str, Any], key: str) -> str:
    item = value[key]
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string")
    return item


def _optional_string(value: dict[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise TypeError(f"{key} must be a string or null")
    return item


def _integer(value: dict[str, Any], key: str) -> int:
    item = value[key]
    if isinstance(item, bool) or not isinstance(item, int):
        raise TypeError(f"{key} must be an integer")
    return item


def _optional_integer(value: dict[str, Any], key: str) -> int | None:
    item = value.get(key)
    if item is not None and (isinstance(item, bool) or not isinstance(item, int)):
        raise TypeError(f"{key} must be an integer or null")
    return item


def _optional_entity_id(value: dict[str, Any], key: str) -> EntityId | None:
    item = _optional_string(value, key)
    return None if item is None else EntityId.from_string(item)


def _execute(session: Session, statement: Any) -> Result[Any]:
    try:
        return session.execute(statement)
    except IntegrityError as exc:
        raise ValueError("persistence constraint rejected the observation") from exc
    except SQLAlchemyError as exc:
        raise ServiceUnavailableError("Local persistence is unavailable") from exc
