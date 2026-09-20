"""Transport-neutral incident timeline and namespace freshness views."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alpha_defense.domain.incidents import (
    CorrelationReason,
    Incident,
    IncidentResolutionCode,
    IncidentStatus,
    IncidentTimelineItemKind,
    NamespaceRiskState,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode


@dataclass(frozen=True, slots=True)
class IncidentTimelineItemView:
    kind: IncidentTimelineItemKind
    occurred_at: datetime
    context_version: int
    entity_id: EntityId | None
    resolution_code: IncidentResolutionCode | None
    correlation_reason: CorrelationReason | None


@dataclass(frozen=True, slots=True)
class IncidentView:
    incident_id: EntityId
    owner_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    status: IncidentStatus
    observation_ids: tuple[EntityId, ...]
    assessment_ids: tuple[EntityId, ...]
    latest_assessment_id: EntityId | None
    context_version: int
    resolution: IncidentResolutionCode | None
    revision: int
    created_at: datetime
    updated_at: datetime
    execution_mode: ExecutionMode
    timeline: tuple[IncidentTimelineItemView, ...]


@dataclass(frozen=True, slots=True)
class NamespaceRiskStateView:
    namespace_id: EntityId
    ingress_risk_epoch: int
    analysis_pending: bool
    pending_observation_ids: tuple[EntityId, ...]
    revision: int


@dataclass(frozen=True, slots=True)
class AttachObservationResult:
    incident: IncidentView
    risk_state: NamespaceRiskStateView
    created_incident: bool


def incident_to_view(incident: Incident) -> IncidentView:
    resolution = incident.resolution
    return IncidentView(
        incident_id=incident.incident_id,
        owner_id=incident.owner_id,
        session_id=incident.session_id,
        namespace_id=incident.namespace_id,
        status=incident.status,
        observation_ids=incident.observation_ids,
        assessment_ids=incident.assessment_ids,
        latest_assessment_id=incident.latest_assessment_id,
        context_version=incident.context_version,
        resolution=None if resolution is None else resolution.code,
        revision=incident.revision,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        execution_mode=incident.execution_mode,
        timeline=tuple(
            IncidentTimelineItemView(
                kind=item.kind,
                occurred_at=item.occurred_at,
                context_version=item.context_version,
                entity_id=item.entity_id,
                resolution_code=item.resolution_code,
                correlation_reason=item.correlation_reason,
            )
            for item in incident.timeline()
        ),
    )


def risk_state_to_view(state: NamespaceRiskState) -> NamespaceRiskStateView:
    return NamespaceRiskStateView(
        namespace_id=state.namespace_id,
        ingress_risk_epoch=state.ingress_risk_epoch,
        analysis_pending=state.analysis_pending,
        pending_observation_ids=tuple(item.observation_id for item in state.pending_analyses),
        revision=state.revision,
    )
