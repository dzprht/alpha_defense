"""Incident aggregate, immutable timeline links, and namespace freshness state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from alpha_defense.domain.incidents.correlation_policy import (
    CorrelationKey,
    CorrelationKeyKind,
    CorrelationReason,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode


class IncidentStatus(StrEnum):
    OPEN = "open"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class IncidentResolutionCode(StrEnum):
    USER_CANCELLED = "user_cancelled"
    FALSE_POSITIVE_REPORTED = "false_positive_reported"
    NO_ACTION_NEEDED = "no_action_needed"
    TRANSFERRED_TO_SUPPORT = "transferred_to_support"


class IncidentTimelineItemKind(StrEnum):
    OBSERVATION = "observation"
    ASSESSMENT = "assessment"
    RESOLUTION = "resolution"


@dataclass(frozen=True, slots=True)
class IncidentObservationLink:
    observation_id: EntityId
    attached_at: datetime
    context_version: int
    correlation_reason: CorrelationReason
    correlation_key: CorrelationKey | None
    available_keys: tuple[CorrelationKey, ...]

    def __post_init__(self) -> None:
        _require_entity_id(self.observation_id, "observation_id")
        _require_utc(self.attached_at, "attached_at")
        _require_positive_int(self.context_version, "context_version")
        if not isinstance(self.correlation_reason, CorrelationReason):
            raise TypeError("correlation_reason must be a CorrelationReason")
        if not isinstance(self.available_keys, tuple) or any(
            not isinstance(key, CorrelationKey) for key in self.available_keys
        ):
            raise TypeError("available_keys must contain CorrelationKey values")
        if len(set(self.available_keys)) != len(self.available_keys):
            raise ValueError("available_keys must be unique")
        if self.correlation_reason is CorrelationReason.NEW_INCIDENT:
            if self.correlation_key is not None:
                raise ValueError("new incidents cannot have a selected correlation key")
            return
        if self.correlation_key is None or self.correlation_key not in self.available_keys:
            raise ValueError("correlated observations require an available selected key")
        expected_kind = {
            CorrelationReason.CONVERSATION: CorrelationKeyKind.CONVERSATION,
            CorrelationReason.CALL: CorrelationKeyKind.CALL,
            CorrelationReason.INDICATOR: CorrelationKeyKind.INDICATOR,
        }[self.correlation_reason]
        if self.correlation_key.kind is not expected_kind:
            raise ValueError("correlation reason does not match the selected key")


@dataclass(frozen=True, slots=True)
class IncidentAssessmentLink:
    assessment_id: EntityId
    assessed_at: datetime
    context_version: int

    def __post_init__(self) -> None:
        _require_entity_id(self.assessment_id, "assessment_id")
        _require_utc(self.assessed_at, "assessed_at")
        _require_positive_int(self.context_version, "context_version")


@dataclass(frozen=True, slots=True)
class IncidentResolution:
    code: IncidentResolutionCode
    resolved_at: datetime
    resolved_by: EntityId
    context_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.code, IncidentResolutionCode):
            raise TypeError("code must be an IncidentResolutionCode")
        _require_utc(self.resolved_at, "resolved_at")
        _require_entity_id(self.resolved_by, "resolved_by")
        _require_positive_int(self.context_version, "context_version")


@dataclass(frozen=True, slots=True)
class IncidentTimelineItem:
    kind: IncidentTimelineItemKind
    occurred_at: datetime
    context_version: int
    entity_id: EntityId | None = None
    resolution_code: IncidentResolutionCode | None = None
    correlation_reason: CorrelationReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, IncidentTimelineItemKind):
            raise TypeError("kind must be an IncidentTimelineItemKind")
        _require_utc(self.occurred_at, "occurred_at")
        _require_positive_int(self.context_version, "context_version")
        if self.kind is IncidentTimelineItemKind.RESOLUTION:
            if self.entity_id is not None or self.resolution_code is None:
                raise ValueError("resolution timeline items require only a resolution code")
            return
        if self.entity_id is None or self.resolution_code is not None:
            raise ValueError("entity timeline items require only an entity id")
        if self.kind is IncidentTimelineItemKind.OBSERVATION and self.correlation_reason is None:
            raise ValueError("observation timeline items require a correlation reason")
        if self.kind is IncidentTimelineItemKind.ASSESSMENT and self.correlation_reason is not None:
            raise ValueError("assessment timeline items cannot have a correlation reason")


@dataclass(frozen=True, slots=True)
class Incident:
    incident_id: EntityId
    owner_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    status: IncidentStatus
    observation_links: tuple[IncidentObservationLink, ...]
    assessment_links: tuple[IncidentAssessmentLink, ...]
    resolution_history: tuple[IncidentResolution, ...]
    context_version: int
    revision: int
    created_at: datetime
    updated_at: datetime
    execution_mode: ExecutionMode

    def __post_init__(self) -> None:
        for name in ("incident_id", "owner_id", "session_id", "namespace_id"):
            _require_entity_id(getattr(self, name), name)
        if not isinstance(self.status, IncidentStatus):
            raise TypeError("status must be an IncidentStatus")
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        _require_positive_int(self.context_version, "context_version")
        _require_non_negative_int(self.revision, "revision")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        self._validate_history()

    @classmethod
    def create(
        cls,
        *,
        incident_id: EntityId,
        owner_id: EntityId,
        session_id: EntityId,
        namespace_id: EntityId,
        observation_id: EntityId,
        available_keys: tuple[CorrelationKey, ...],
        created_at: datetime,
        execution_mode: ExecutionMode,
    ) -> Incident:
        return cls(
            incident_id=incident_id,
            owner_id=owner_id,
            session_id=session_id,
            namespace_id=namespace_id,
            status=IncidentStatus.OPEN,
            observation_links=(
                IncidentObservationLink(
                    observation_id=observation_id,
                    attached_at=created_at,
                    context_version=1,
                    correlation_reason=CorrelationReason.NEW_INCIDENT,
                    correlation_key=None,
                    available_keys=available_keys,
                ),
            ),
            assessment_links=(),
            resolution_history=(),
            context_version=1,
            revision=0,
            created_at=created_at,
            updated_at=created_at,
            execution_mode=execution_mode,
        )

    @property
    def observation_ids(self) -> tuple[EntityId, ...]:
        return tuple(link.observation_id for link in self.observation_links)

    @property
    def assessment_ids(self) -> tuple[EntityId, ...]:
        return tuple(link.assessment_id for link in self.assessment_links)

    @property
    def latest_assessment_id(self) -> EntityId | None:
        return None if not self.assessment_links else self.assessment_links[-1].assessment_id

    @property
    def resolution(self) -> IncidentResolution | None:
        if self.status is not IncidentStatus.RESOLVED:
            return None
        return self.resolution_history[-1]

    def attach_observation(
        self,
        *,
        observation_id: EntityId,
        available_keys: tuple[CorrelationKey, ...],
        correlation_reason: CorrelationReason,
        correlation_key: CorrelationKey,
        attached_at: datetime,
    ) -> Incident:
        if observation_id in self.observation_ids:
            raise ValueError("observation is already attached to the incident")
        link = IncidentObservationLink(
            observation_id=observation_id,
            attached_at=attached_at,
            context_version=self.context_version + 1,
            correlation_reason=correlation_reason,
            correlation_key=correlation_key,
            available_keys=available_keys,
        )
        return replace(
            self,
            status=IncidentStatus.OPEN,
            observation_links=(*self.observation_links, link),
            context_version=self.context_version + 1,
            revision=self.revision + 1,
            updated_at=attached_at,
        )

    def record_assessment(
        self,
        *,
        assessment_id: EntityId,
        context_version: int,
        assessed_at: datetime,
    ) -> Incident:
        if self.status is IncidentStatus.RESOLVED:
            raise ValueError("resolved incidents require new evidence before assessment")
        if assessment_id in self.assessment_ids:
            raise ValueError("assessment is already attached to the incident")
        if context_version != self.context_version:
            raise ValueError("assessment context_version is stale")
        link = IncidentAssessmentLink(
            assessment_id=assessment_id,
            assessed_at=assessed_at,
            context_version=context_version,
        )
        return replace(
            self,
            status=IncidentStatus.MONITORING,
            assessment_links=(*self.assessment_links, link),
            revision=self.revision + 1,
            updated_at=assessed_at,
        )

    def resolve(
        self,
        *,
        code: IncidentResolutionCode,
        resolved_at: datetime,
        resolved_by: EntityId,
    ) -> Incident:
        if self.status is IncidentStatus.RESOLVED:
            raise ValueError("incident is already resolved")
        resolution = IncidentResolution(
            code=code,
            resolved_at=resolved_at,
            resolved_by=resolved_by,
            context_version=self.context_version,
        )
        return replace(
            self,
            status=IncidentStatus.RESOLVED,
            resolution_history=(*self.resolution_history, resolution),
            revision=self.revision + 1,
            updated_at=resolved_at,
        )

    def timeline(self) -> tuple[IncidentTimelineItem, ...]:
        ordered: list[tuple[datetime, int, int, IncidentTimelineItem]] = []
        for ordinal, observation_link in enumerate(self.observation_links):
            ordered.append(
                (
                    observation_link.attached_at,
                    0,
                    ordinal,
                    IncidentTimelineItem(
                        kind=IncidentTimelineItemKind.OBSERVATION,
                        occurred_at=observation_link.attached_at,
                        context_version=observation_link.context_version,
                        entity_id=observation_link.observation_id,
                        correlation_reason=observation_link.correlation_reason,
                    ),
                )
            )
        for ordinal, assessment_link in enumerate(self.assessment_links):
            ordered.append(
                (
                    assessment_link.assessed_at,
                    1,
                    ordinal,
                    IncidentTimelineItem(
                        kind=IncidentTimelineItemKind.ASSESSMENT,
                        occurred_at=assessment_link.assessed_at,
                        context_version=assessment_link.context_version,
                        entity_id=assessment_link.assessment_id,
                    ),
                )
            )
        for ordinal, resolution in enumerate(self.resolution_history):
            ordered.append(
                (
                    resolution.resolved_at,
                    2,
                    ordinal,
                    IncidentTimelineItem(
                        kind=IncidentTimelineItemKind.RESOLUTION,
                        occurred_at=resolution.resolved_at,
                        context_version=resolution.context_version,
                        resolution_code=resolution.code,
                    ),
                )
            )
        return tuple(item[-1] for item in sorted(ordered, key=lambda item: item[:3]))

    def _validate_history(self) -> None:
        if not isinstance(self.observation_links, tuple) or not self.observation_links:
            raise ValueError("incident requires at least one observation")
        if any(not isinstance(link, IncidentObservationLink) for link in self.observation_links):
            raise TypeError("observation_links must contain IncidentObservationLink values")
        observation_ids = self.observation_ids
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("incident observation ids must be unique")
        versions = tuple(link.context_version for link in self.observation_links)
        if versions != tuple(range(1, len(self.observation_links) + 1)):
            raise ValueError("observation context versions must be contiguous")
        if self.context_version != len(self.observation_links):
            raise ValueError("context_version must equal the observation history length")
        if self.created_at != self.observation_links[0].attached_at:
            raise ValueError("created_at must match the first observation")
        if any(link.attached_at < self.created_at for link in self.observation_links):
            raise ValueError("observation history cannot precede incident creation")
        if not isinstance(self.assessment_links, tuple) or any(
            not isinstance(link, IncidentAssessmentLink) for link in self.assessment_links
        ):
            raise TypeError("assessment_links must contain IncidentAssessmentLink values")
        if len(set(self.assessment_ids)) != len(self.assessment_ids):
            raise ValueError("incident assessment ids must be unique")
        if any(link.context_version > self.context_version for link in self.assessment_links):
            raise ValueError("assessment cannot reference a future context version")
        if not isinstance(self.resolution_history, tuple) or any(
            not isinstance(item, IncidentResolution) for item in self.resolution_history
        ):
            raise TypeError("resolution_history must contain IncidentResolution values")
        if any(item.context_version > self.context_version for item in self.resolution_history):
            raise ValueError("resolution cannot reference a future context version")
        if self.status is IncidentStatus.RESOLVED and not self.resolution_history:
            raise ValueError("resolved incidents require a resolution")
        if self.status is IncidentStatus.MONITORING and not self.assessment_links:
            raise ValueError("monitoring incidents require an assessment")
        history_times = (
            *(link.attached_at for link in self.observation_links),
            *(link.assessed_at for link in self.assessment_links),
            *(item.resolved_at for item in self.resolution_history),
        )
        if any(value > self.updated_at for value in history_times):
            raise ValueError("updated_at cannot precede timeline history")


@dataclass(frozen=True, slots=True)
class PendingAnalysis:
    observation_id: EntityId
    incident_id: EntityId
    accepted_at: datetime

    def __post_init__(self) -> None:
        _require_entity_id(self.observation_id, "observation_id")
        _require_entity_id(self.incident_id, "incident_id")
        _require_utc(self.accepted_at, "accepted_at")


@dataclass(frozen=True, slots=True)
class NamespaceRiskState:
    namespace_id: EntityId
    owner_id: EntityId
    session_id: EntityId
    ingress_risk_epoch: int
    pending_analyses: tuple[PendingAnalysis, ...]
    revision: int
    updated_at: datetime
    execution_mode: ExecutionMode

    def __post_init__(self) -> None:
        for name in ("namespace_id", "owner_id", "session_id"):
            _require_entity_id(getattr(self, name), name)
        _require_positive_int(self.ingress_risk_epoch, "ingress_risk_epoch")
        _require_non_negative_int(self.revision, "revision")
        _require_utc(self.updated_at, "updated_at")
        if not isinstance(self.pending_analyses, tuple) or any(
            not isinstance(item, PendingAnalysis) for item in self.pending_analyses
        ):
            raise TypeError("pending_analyses must contain PendingAnalysis values")
        pending_ids = tuple(item.observation_id for item in self.pending_analyses)
        if len(set(pending_ids)) != len(pending_ids):
            raise ValueError("pending observation ids must be unique")
        if any(item.accepted_at > self.updated_at for item in self.pending_analyses):
            raise ValueError("updated_at cannot precede pending analysis")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")

    @classmethod
    def create(
        cls,
        *,
        namespace_id: EntityId,
        owner_id: EntityId,
        session_id: EntityId,
        observation_id: EntityId,
        incident_id: EntityId,
        accepted_at: datetime,
        execution_mode: ExecutionMode,
    ) -> NamespaceRiskState:
        return cls(
            namespace_id=namespace_id,
            owner_id=owner_id,
            session_id=session_id,
            ingress_risk_epoch=1,
            pending_analyses=(
                PendingAnalysis(
                    observation_id=observation_id,
                    incident_id=incident_id,
                    accepted_at=accepted_at,
                ),
            ),
            revision=0,
            updated_at=accepted_at,
            execution_mode=execution_mode,
        )

    @property
    def analysis_pending(self) -> bool:
        return bool(self.pending_analyses)

    def is_pending(self, observation_id: EntityId) -> bool:
        return any(item.observation_id == observation_id for item in self.pending_analyses)

    def accept(
        self,
        *,
        observation_id: EntityId,
        incident_id: EntityId,
        accepted_at: datetime,
    ) -> NamespaceRiskState:
        if self.is_pending(observation_id):
            raise ValueError("observation is already pending analysis")
        if accepted_at < self.updated_at:
            raise ValueError("accepted_at cannot precede the current state")
        return replace(
            self,
            ingress_risk_epoch=self.ingress_risk_epoch + 1,
            pending_analyses=(
                *self.pending_analyses,
                PendingAnalysis(
                    observation_id=observation_id,
                    incident_id=incident_id,
                    accepted_at=accepted_at,
                ),
            ),
            revision=self.revision + 1,
            updated_at=accepted_at,
        )

    def complete(self, *, observation_id: EntityId, completed_at: datetime) -> NamespaceRiskState:
        if not self.is_pending(observation_id):
            raise ValueError("observation is not pending analysis")
        if completed_at < self.updated_at:
            raise ValueError("completed_at cannot precede the current state")
        return replace(
            self,
            pending_analyses=tuple(
                item for item in self.pending_analyses if item.observation_id != observation_id
            ),
            revision=self.revision + 1,
            updated_at=completed_at,
        )


def _require_entity_id(value: object, field_name: str) -> None:
    if not isinstance(value, EntityId):
        raise TypeError(f"{field_name} must be an EntityId")


def _require_utc(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC-aware")


def _require_non_negative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive_int(value: object, field_name: str) -> None:
    _require_non_negative_int(value, field_name)
    if value == 0:
        raise ValueError(f"{field_name} must be positive")
