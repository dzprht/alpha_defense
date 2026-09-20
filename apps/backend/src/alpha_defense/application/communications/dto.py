"""Transport-neutral commands and views for communication observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alpha_defense.domain.communications import (
    NormalizedIndicator,
    ObservationKind,
    ObservationPayload,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode


@dataclass(frozen=True, slots=True)
class ObservationInput:
    source_event_id: str
    occurred_at: datetime
    payload: ObservationPayload


@dataclass(frozen=True, slots=True)
class ObservationView:
    observation_id: EntityId
    owner_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    kind: ObservationKind
    source: str
    source_event_id: str
    occurred_at: datetime
    received_at: datetime
    payload: ObservationPayload
    normalized_indicators: tuple[NormalizedIndicator, ...]
    media_refs: tuple[EntityId, ...]
    normalization_version: str
    execution_mode: ExecutionMode


@dataclass(frozen=True, slots=True)
class IngestObservationResult:
    observation: ObservationView
    duplicate: bool
