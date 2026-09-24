"""Public, owner-scoped contact and assessment representations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from alpha_defense.application.communications import ObservationView
from alpha_defense.application.communications.mapping import payload_to_data
from alpha_defense.application.detection import RiskAssessment
from alpha_defense.application.education import GuidanceView
from alpha_defense.application.incidents import IncidentView
from alpha_defense.application.workflows import ContactAnalysisResult
from alpha_defense.transport.http.v1.schemas.observations import (
    CallTranscriptPayloadSchema,
    SmsPayloadSchema,
    WebResourcePayloadSchema,
)


class NormalizedIndicatorResponse(BaseModel):
    indicator_type: str
    origin: str
    normalized_value: str | None
    status: str
    normalization_version: str


class TimelineItemResponse(BaseModel):
    kind: str
    occurred_at: datetime
    context_version: int
    entity_id: str | None
    resolution_code: str | None
    correlation_reason: str | None


class SignalResponse(BaseModel):
    code: str
    evidence_ref: str
    strength: int
    source: str


class AnalyzerResultResponse(BaseModel):
    analyzer: str
    status: str
    reason_codes: list[str]
    model_score: float | None
    provider: str
    provider_version: str
    data_version: str


class RecommendationResponse(BaseModel):
    code: str
    title: str
    body: str


class EducationCardReferenceResponse(BaseModel):
    code: str
    version: str


class AllowedActionResponse(BaseModel):
    code: str
    enabled: bool
    disabled_reason: str | None
    requires_confirmation: bool
    target_id: str
    target_revision: int


class TrustedSupportContactResponse(BaseModel):
    code: str
    value: str


class ObservationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    kind: str
    source_event_id: str
    occurred_at: datetime
    received_at: datetime
    payload: SmsPayloadSchema | CallTranscriptPayloadSchema | WebResourcePayloadSchema
    normalized_indicators: list[NormalizedIndicatorResponse]
    normalization_version: str
    execution_mode: str

    @classmethod
    def from_view(cls, view: ObservationView) -> ObservationResponse:
        return cls(
            observation_id=str(view.observation_id),
            kind=view.kind.value,
            source_event_id=view.source_event_id,
            occurred_at=view.occurred_at,
            received_at=view.received_at,
            payload=payload_to_data(view.payload),
            normalized_indicators=[
                NormalizedIndicatorResponse(
                    indicator_type=item.indicator_type.value,
                    origin=item.origin.value,
                    normalized_value=item.normalized_value,
                    status=item.status.value,
                    normalization_version=item.normalization_version,
                )
                for item in view.normalized_indicators
            ],
            normalization_version=view.normalization_version,
            execution_mode=view.execution_mode.value,
        )


class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    status: str
    observation_ids: list[str]
    assessment_ids: list[str]
    latest_assessment_id: str | None
    resolution: str | None
    context_version: int
    revision: int
    created_at: datetime
    updated_at: datetime
    execution_mode: str
    timeline: list[TimelineItemResponse]

    @classmethod
    def from_view(cls, view: IncidentView) -> IncidentResponse:
        return cls(
            incident_id=str(view.incident_id),
            status=view.status.value,
            observation_ids=[str(value) for value in view.observation_ids],
            assessment_ids=[str(value) for value in view.assessment_ids],
            latest_assessment_id=(
                None if view.latest_assessment_id is None else str(view.latest_assessment_id)
            ),
            resolution=None if view.resolution is None else view.resolution.value,
            context_version=view.context_version,
            revision=view.revision,
            created_at=view.created_at,
            updated_at=view.updated_at,
            execution_mode=view.execution_mode.value,
            timeline=[
                TimelineItemResponse(
                    kind=item.kind.value,
                    occurred_at=item.occurred_at,
                    context_version=item.context_version,
                    entity_id=None if item.entity_id is None else str(item.entity_id),
                    resolution_code=(
                        None if item.resolution_code is None else item.resolution_code.value
                    ),
                    correlation_reason=(
                        None if item.correlation_reason is None else item.correlation_reason.value
                    ),
                )
                for item in view.timeline
            ],
        )


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: str
    target_id: str
    severity: str
    score: int | None
    score_kind: str
    completeness: str
    reason_codes: list[str]
    signals: list[SignalResponse]
    analyzer_results: list[AnalyzerResultResponse]
    policy_version: str
    analysis_plan_version: str
    assessed_at: datetime
    context_version: int
    has_mock_evidence: bool

    @classmethod
    def from_assessment(cls, value: RiskAssessment) -> AssessmentResponse:
        return cls(
            assessment_id=str(value.assessment_id),
            target_id=str(value.target_id),
            severity=value.severity.value,
            score=value.score,
            score_kind=value.score_kind,
            completeness=value.completeness.value,
            reason_codes=list(value.reason_codes),
            signals=[
                SignalResponse(
                    code=item.code,
                    evidence_ref=item.evidence_ref,
                    strength=item.strength,
                    source=item.source,
                )
                for item in value.signals
            ],
            analyzer_results=[
                AnalyzerResultResponse(
                    analyzer=item.analyzer.value,
                    status=item.status.value,
                    reason_codes=list(item.reason_codes),
                    model_score=item.model_score,
                    provider=item.provenance.provider,
                    provider_version=item.provenance.provider_version,
                    data_version=item.provenance.data_version,
                )
                for item in value.analyzer_results
            ],
            policy_version=value.policy_version,
            analysis_plan_version=value.analysis_plan_version,
            assessed_at=value.assessed_at,
            context_version=value.context_version,
            has_mock_evidence=value.has_mock_evidence,
        )


class GuidanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_label: str
    explanation: str
    classification: str
    completeness: str
    recommendations: list[RecommendationResponse]
    education_cards: list[EducationCardReferenceResponse]
    allowed_actions: list[AllowedActionResponse]
    support_message: str | None
    support_contact: TrustedSupportContactResponse | None
    unmapped_reason_codes: list[str]
    locale: str
    requested_locale: str
    content_version: str

    @classmethod
    def from_view(cls, view: GuidanceView) -> GuidanceResponse:
        return cls(
            risk_label=view.risk_label,
            explanation=view.explanation,
            classification=view.classification.value,
            completeness=view.completeness.value,
            recommendations=[
                RecommendationResponse(code=item.code, title=item.title, body=item.body)
                for item in view.recommendations
            ],
            education_cards=[
                EducationCardReferenceResponse(code=item.code, version=item.version)
                for item in view.education_cards
            ],
            allowed_actions=[
                AllowedActionResponse(
                    code=item.code,
                    enabled=item.enabled,
                    disabled_reason=item.disabled_reason,
                    requires_confirmation=item.requires_confirmation,
                    target_id=str(item.target_id),
                    target_revision=item.target_revision,
                )
                for item in view.allowed_actions
            ],
            support_message=view.support_message,
            support_contact=(
                None
                if view.support_contact is None
                else TrustedSupportContactResponse(
                    code=view.support_contact.code, value=view.support_contact.value
                )
            ),
            unmapped_reason_codes=list(view.unmapped_reason_codes),
            locale=view.locale,
            requested_locale=view.requested_locale,
            content_version=view.content_version,
        )


class ContactAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    incident_id: str
    incident_context_version: int
    analysis_pending: bool
    assessment: AssessmentResponse
    warning_id: str | None
    warning_dispatched: bool
    duplicate_source_event: bool

    @classmethod
    def from_result(cls, value: ContactAnalysisResult) -> ContactAnalysisResponse:
        return cls(
            observation_id=str(value.observation.observation_id),
            incident_id=str(value.incident.incident_id),
            incident_context_version=value.incident.context_version,
            analysis_pending=value.risk_state.analysis_pending,
            assessment=AssessmentResponse.from_assessment(value.assessment),
            warning_id=None if value.warning is None else str(value.warning.warning_id),
            warning_dispatched=(
                value.warning is not None and value.warning.dispatched_at is not None
            ),
            duplicate_source_event=value.duplicate_source_event,
        )
