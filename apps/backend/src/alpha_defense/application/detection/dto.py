"""Transport-neutral input for assessing one persisted observation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from alpha_defense.domain.communications import (
    CommunicationIndicatorType,
    NormalizationStatus,
    NormalizedIndicator,
    ObservationKind,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode


class ThreatEvidenceOutcome(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ThreatLookupEvidence:
    outcome: ThreatEvidenceOutcome
    evidence_refs: tuple[str, ...]
    snapshot_version: str | None
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ThreatEvidenceOutcome):
            raise TypeError("outcome must be a ThreatEvidenceOutcome")
        if not isinstance(self.evidence_refs, tuple) or any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in self.evidence_refs
        ):
            raise ValueError("evidence_refs must contain non-empty trimmed strings")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        if self.outcome is ThreatEvidenceOutcome.MATCH and not self.evidence_refs:
            raise ValueError("matched threat evidence requires evidence_refs")
        if self.outcome is not ThreatEvidenceOutcome.MATCH and self.evidence_refs:
            raise ValueError("non-match threat evidence cannot contain evidence_refs")
        if self.snapshot_version is not None and (
            not isinstance(self.snapshot_version, str)
            or not self.snapshot_version
            or self.snapshot_version != self.snapshot_version.strip()
        ):
            raise ValueError("snapshot_version must be non-empty and trimmed")
        if not isinstance(self.reason_code, str) or not self.reason_code:
            raise ValueError("reason_code must be non-empty")


@dataclass(frozen=True, slots=True)
class ObservationAnalysisInput:
    observation_id: EntityId
    owner_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    kind: ObservationKind
    text: str | None
    raw_resource_url: str | None
    normalized_resource_url: str | None
    normalized_indicators: tuple[NormalizedIndicator, ...]
    media_refs: tuple[EntityId, ...]
    context_version: int
    execution_mode: ExecutionMode

    def __post_init__(self) -> None:
        for field_name in ("observation_id", "owner_id", "session_id", "namespace_id"):
            if not isinstance(getattr(self, field_name), EntityId):
                raise TypeError(f"{field_name} must be an EntityId")
        if not isinstance(self.kind, ObservationKind):
            raise TypeError("kind must be an ObservationKind")
        text_kinds = {
            ObservationKind.SMS,
            ObservationKind.MESSENGER,
            ObservationKind.CALL_TRANSCRIPT,
        }
        if self.kind in text_kinds:
            if not isinstance(self.text, str) or not self.text.strip():
                raise ValueError("text observations require non-empty text")
            if self.raw_resource_url is not None or self.normalized_resource_url is not None:
                raise ValueError("text observations cannot contain a resource URL")
        elif self.text is not None:
            raise ValueError("web observations cannot contain text")
        if self.raw_resource_url is not None and (
            not isinstance(self.raw_resource_url, str) or not self.raw_resource_url.strip()
        ):
            raise ValueError("raw_resource_url must be non-empty when present")
        if self.normalized_resource_url is not None and self.raw_resource_url is None:
            raise ValueError("normalized_resource_url requires raw_resource_url")
        if self.kind is ObservationKind.WEB_RESOURCE and not (
            self.raw_resource_url is not None or self.media_refs
        ):
            raise ValueError("web observations require a URL or media reference")
        if not isinstance(self.normalized_indicators, tuple) or any(
            not isinstance(item, NormalizedIndicator)
            or item.status is not NormalizationStatus.NORMALIZED
            for item in self.normalized_indicators
        ):
            raise ValueError("normalized_indicators must contain normalized values")
        if not isinstance(self.media_refs, tuple) or any(
            not isinstance(item, EntityId) for item in self.media_refs
        ):
            raise TypeError("media_refs must contain EntityId values")
        if isinstance(self.context_version, bool) or not isinstance(self.context_version, int):
            raise TypeError("context_version must be an integer")
        if self.context_version < 1:
            raise ValueError("context_version must be positive")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")

    @property
    def has_lookup_indicators(self) -> bool:
        return any(
            item.indicator_type
            in {
                CommunicationIndicatorType.PHONE,
                CommunicationIndicatorType.URL,
                CommunicationIndicatorType.DOMAIN,
            }
            for item in self.normalized_indicators
        )
