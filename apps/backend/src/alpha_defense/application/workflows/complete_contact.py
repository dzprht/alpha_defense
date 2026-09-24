"""Complete contact analysis after intake without holding a transaction during inference."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_defense.application.communications import ObservationInput, ObservationView
from alpha_defense.application.communications.ingest_observation import to_view
from alpha_defense.application.communications.mapping import canonical_sha256
from alpha_defense.application.detection import (
    AssessObservation,
    ObservationAnalysisInput,
    ThreatEvidenceOutcome,
    ThreatLookupEvidence,
)
from alpha_defense.application.education import GetGuidance, GuidanceView
from alpha_defense.application.incidents.dto import (
    IncidentView,
    NamespaceRiskStateView,
    incident_to_view,
    risk_state_to_view,
)
from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    ContactUnitOfWorkFactory,
    ContactUnitOfWorkPort,
    EventEnvelope,
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    IdGenerator,
    OutboxMessage,
    OutboxState,
)
from alpha_defense.application.protection import WarningDraft, WarningService
from alpha_defense.application.shared import (
    ActionForbiddenError,
    ActorContext,
    IdempotencyConflictError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    StaleRevisionError,
)
from alpha_defense.application.threats import LookupThreatIndicators, ThreatLookupOutcome
from alpha_defense.application.workflows.analyze_contact import AnalyzeContact
from alpha_defense.domain.communications import (
    CallTranscriptPayload,
    CommunicationIndicatorType,
    MessengerPayload,
    NormalizationStatus,
    SmsPayload,
    WebResourcePayload,
)
from alpha_defense.domain.detection import RiskAssessment
from alpha_defense.domain.identity import ConsentScope, ConsentStatus
from alpha_defense.domain.incidents import Incident
from alpha_defense.domain.protection import Warning, WarningCompleteness, WarningTargetKind
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import IndicatorType, ThreatIndicator


@dataclass(frozen=True, slots=True)
class ContactAnalysisResult:
    observation: ObservationView
    incident: IncidentView
    risk_state: NamespaceRiskStateView
    assessment: RiskAssessment
    warning: Warning | None
    duplicate_source_event: bool


class CompleteContactAnalysis:
    """Separate intake and inference, then atomically publish the current assessment."""

    def __init__(
        self,
        *,
        unit_of_work: ContactUnitOfWorkFactory,
        intake: AnalyzeContact,
        assess: AssessObservation,
        lookup_threats: LookupThreatIndicators,
        guidance: GetGuidance,
        warnings: WarningService,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._intake = intake
        self._assess = assess
        self._lookup_threats = lookup_threats
        self._guidance = guidance
        self._warnings = warnings
        self._clock = clock
        self._id_generator = id_generator

    def submit(
        self,
        *,
        actor: ActorContext,
        observation_input: ObservationInput,
        idempotency_key: str,
    ) -> ContactAnalysisResult:
        self._require_consent(actor, observation_input.payload)
        receipt = self._intake.execute(
            actor=actor,
            source="manual.web",
            observation_input=observation_input,
            idempotency_key=idempotency_key,
        )
        return self._evaluate_and_commit(
            actor=actor,
            observation_id=receipt.observation.observation_id,
            expected_incident_id=receipt.incident.incident_id,
            expected_context_version=receipt.incident.context_version,
            duplicate_source_event=receipt.duplicate_source_event,
            reuse_existing=True,
        )

    def reassess(
        self,
        *,
        actor: ActorContext,
        observation_id: EntityId,
        idempotency_key: str | None = None,
    ) -> ContactAnalysisResult:
        with self._unit_of_work() as uow:
            stored = uow.observations.get(observation_id)
            incident = uow.incidents.get_by_observation(observation_id)
            if stored is None or incident is None or not _owned(incident, actor):
                raise ResourceNotFoundError("Наблюдение не найдено.")
            self._require_consent_in_uow(uow, actor, stored.content.payload)
            if idempotency_key is not None:
                scope = _reassessment_scope(actor, idempotency_key)
                existing = uow.idempotency.get(scope)
                if existing is not None:
                    if existing.command_hash != canonical_sha256(
                        {"observation_id": str(observation_id)}
                    ):
                        raise IdempotencyConflictError(
                            "The idempotency key was already used with a different command"
                        )
                    if existing.state is not IdempotencyState.COMPLETED or existing.result is None:
                        raise ServiceUnavailableError("Reassessment replay is incomplete")
                    old_id = existing.result.get("assessment_id")
                    if not isinstance(old_id, str):
                        raise ServiceUnavailableError("Reassessment replay is invalid")
                    old_assessment = uow.assessments.get(EntityId.from_string(old_id))
                    state = uow.namespace_risk_states.get(actor.namespace_id)
                    if old_assessment is None or state is None:
                        raise ServiceUnavailableError("Reassessment replay is missing")
                    return ContactAnalysisResult(
                        observation=to_view(stored),
                        incident=incident_to_view(incident),
                        risk_state=risk_state_to_view(state),
                        assessment=old_assessment,
                        warning=uow.warnings.get_by_assessment(old_assessment.assessment_id),
                        duplicate_source_event=False,
                    )
            incident_id = incident.incident_id
            context_version = incident.context_version
        return self._evaluate_and_commit(
            actor=actor,
            observation_id=observation_id,
            expected_incident_id=incident_id,
            expected_context_version=context_version,
            duplicate_source_event=False,
            reuse_existing=False,
            reassessment_key=idempotency_key,
        )

    def get_assessment(self, *, actor: ActorContext, assessment_id: EntityId) -> RiskAssessment:
        with self._unit_of_work() as uow:
            assessment = uow.assessments.get(assessment_id)
        if assessment is None or not _owned_assessment(assessment, actor):
            raise ResourceNotFoundError("Оценка риска не найдена.")
        return assessment

    def get_guidance(
        self, *, actor: ActorContext, assessment_id: EntityId, locale: str = "ru-RU"
    ) -> GuidanceView:
        assessment = self.get_assessment(actor=actor, assessment_id=assessment_id)
        return self._guidance.execute(
            actor=actor, assessment=assessment, allowed_actions=(), locale=locale
        )

    def _require_consent(self, actor: ActorContext, payload: object) -> None:
        with self._unit_of_work() as uow:
            self._require_consent_in_uow(uow, actor, payload)

    @staticmethod
    def _require_consent_in_uow(
        uow: ContactUnitOfWorkPort, actor: ActorContext, payload: object
    ) -> None:
        # The contact UoW also owns identity snapshots; no HTTP field grants consent.
        scope = (
            ConsentScope.ANALYZE_RESOURCES
            if isinstance(payload, WebResourcePayload)
            else ConsentScope.ANALYZE_COMMUNICATIONS
        )
        consent = uow.identity.get_consent(actor.user_id, scope)
        if consent is None or consent.status is not ConsentStatus.GRANTED:
            raise ActionForbiddenError("Для проверки требуется явное согласие.")

    def _evaluate_and_commit(
        self,
        *,
        actor: ActorContext,
        observation_id: EntityId,
        expected_incident_id: EntityId,
        expected_context_version: int,
        duplicate_source_event: bool,
        reuse_existing: bool,
        reassessment_key: str | None = None,
    ) -> ContactAnalysisResult:
        with self._unit_of_work() as uow:
            stored = uow.observations.get(observation_id)
            incident = uow.incidents.get(expected_incident_id)
            if stored is None or incident is None or not _owned(incident, actor):
                raise ResourceNotFoundError("Наблюдение не найдено.")
            if observation_id not in incident.observation_ids:
                raise ResourceNotFoundError("Наблюдение не найдено.")
            if incident.context_version != expected_context_version:
                raise StaleRevisionError("Контекст инцидента изменился. Повторите проверку.")
            initial_revision = incident.revision
            existing = uow.assessments.list_for_observation(observation_id)
            if reuse_existing:
                # A repeated source event is not a reassessment command. Once it
                # has a result, later evidence must not make a replay analyze it
                # again or clear the newer observation's pending state.
                current = existing[-1] if existing else None
                if current is not None:
                    state = uow.namespace_risk_states.get(actor.namespace_id)
                    if state is None:
                        raise ServiceUnavailableError("Namespace risk state is missing")
                    return ContactAnalysisResult(
                        observation=to_view(stored),
                        incident=incident_to_view(incident),
                        risk_state=risk_state_to_view(state),
                        assessment=current,
                        warning=uow.warnings.get_by_assessment(current.assessment_id),
                        duplicate_source_event=duplicate_source_event,
                    )
            analysis_input = _analysis_input(to_view(stored), expected_context_version)

        threat_evidence = self._lookup(analysis_input)
        assessment = self._assess.execute(
            actor=actor, observation=analysis_input, threat_evidence=threat_evidence
        )
        with self._unit_of_work() as uow:
            incident = uow.incidents.get(expected_incident_id)
            stored = uow.observations.get(observation_id)
            state = uow.namespace_risk_states.get(actor.namespace_id)
            if (
                incident is None
                or stored is None
                or state is None
                or not _owned(incident, actor)
                or observation_id not in incident.observation_ids
            ):
                raise ResourceNotFoundError("Наблюдение не найдено.")
            if (
                incident.context_version != expected_context_version
                or incident.revision != initial_revision
            ):
                raise StaleRevisionError("Контекст инцидента изменился. Повторите проверку.")
            self._require_consent_in_uow(uow, actor, stored.content.payload)
            reservation = None
            if reassessment_key is not None:
                now = self._clock.now_utc()
                reservation = uow.idempotency.reserve(
                    IdempotencyRecord(
                        record_id=self._id_generator.new_id(),
                        scope=_reassessment_scope(actor, reassessment_key),
                        command_hash=canonical_sha256({"observation_id": str(observation_id)}),
                        resource_id=assessment.assessment_id,
                        state=IdempotencyState.IN_PROGRESS,
                        result=None,
                        revision=0,
                        created_at=now,
                        updated_at=now,
                    )
                )
                if not reservation.is_new:
                    raise StaleRevisionError("Повторная проверка уже выполнена. Повторите запрос.")
            uow.assessments.add(assessment)
            updated_incident = incident.record_assessment(
                assessment_id=assessment.assessment_id,
                context_version=assessment.context_version,
                assessed_at=assessment.assessed_at,
            )
            uow.incidents.save(updated_incident, expected_revision=incident.revision)
            updated_state = (
                state.complete(observation_id=observation_id, completed_at=self._clock.now_utc())
                if state.is_pending(observation_id)
                else state
            )
            if updated_state is not state:
                uow.namespace_risk_states.save(updated_state, expected_revision=state.revision)
            warning = self._warnings.create_in_unit_of_work(
                uow=uow,
                actor=actor,
                draft=self._warning_draft(actor, assessment),
            )
            if warning is not None:
                dispatched = warning.dispatch(self._clock.now_utc())
                uow.warnings.save(dispatched, expected_revision=warning.revision)
                warning = dispatched
                self._outbox_warning(uow, actor, warning)
            self._audit_assessment(uow, actor, assessment, updated_incident.revision)
            if reservation is not None:
                uow.idempotency.save(
                    reservation.record.finish(
                        state=IdempotencyState.COMPLETED,
                        result={"assessment_id": str(assessment.assessment_id)},
                        updated_at=self._clock.now_utc(),
                    ),
                    expected_revision=0,
                )
            uow.commit()
        return ContactAnalysisResult(
            observation=to_view(stored),
            incident=incident_to_view(updated_incident),
            risk_state=risk_state_to_view(updated_state),
            assessment=assessment,
            warning=warning,
            duplicate_source_event=duplicate_source_event,
        )

    def _warning_draft(self, actor: ActorContext, assessment: RiskAssessment) -> WarningDraft:
        guidance = self._guidance.execute(actor=actor, assessment=assessment, allowed_actions=())
        return WarningDraft(
            assessment_id=assessment.assessment_id,
            target_kind=WarningTargetKind(assessment.target_kind.value),
            target_id=assessment.target_id,
            context_version=assessment.context_version,
            severity=assessment.severity,
            completeness=WarningCompleteness(assessment.completeness.value),
            risk_label=guidance.risk_label,
            explanation=guidance.explanation,
            content_version=guidance.content_version,
            allowed_actions=(),
        )

    def _lookup(self, observation: ObservationAnalysisInput) -> ThreatLookupEvidence | None:
        indicators = tuple(
            sorted(
                {
                    ThreatIndicator(
                        indicator_type=IndicatorType(item.indicator_type.value),
                        normalized_value=item.normalized_value,
                    )
                    for item in observation.normalized_indicators
                    if item.normalized_value is not None
                },
                key=lambda item: (item.indicator_type.value, item.normalized_value),
            )
        )
        if not indicators:
            return None
        try:
            results = self._lookup_threats.execute(indicators)
        except ServiceUnavailableError:
            return ThreatLookupEvidence(
                outcome=ThreatEvidenceOutcome.UNAVAILABLE,
                evidence_refs=(),
                snapshot_version=None,
                reason_code="registry_unavailable",
            )
        unavailable = next(
            (item for item in results if item.outcome is ThreatLookupOutcome.UNAVAILABLE), None
        )
        if unavailable is not None:
            return ThreatLookupEvidence(
                outcome=ThreatEvidenceOutcome.UNAVAILABLE,
                evidence_refs=(),
                snapshot_version=unavailable.snapshot_version,
                reason_code=unavailable.reason_code,
            )
        refs = tuple(sorted({match.evidence_ref for item in results for match in item.matches}))
        return ThreatLookupEvidence(
            outcome=ThreatEvidenceOutcome.MATCH if refs else ThreatEvidenceOutcome.NO_MATCH,
            evidence_refs=refs,
            snapshot_version=results[0].snapshot_version,
            reason_code="active_exact_match" if refs else "no_active_match",
        )

    def _audit_assessment(
        self,
        uow: ContactUnitOfWorkPort,
        actor: ActorContext,
        assessment: RiskAssessment,
        revision: int,
    ) -> None:
        uow.audit.append(
            AuditRecord(
                event=EventEnvelope(
                    event_id=self._id_generator.new_id(),
                    event_type="assessment.created",
                    aggregate_id=assessment.assessment_id,
                    aggregate_revision=revision,
                    occurred_at=assessment.assessed_at,
                    correlation_id=assessment.target_id,
                    execution_mode=actor.execution_mode,
                    payload={
                        "severity": assessment.severity.value,
                        "completeness": assessment.completeness.value,
                        "context_version": assessment.context_version,
                        "policy_version": assessment.policy_version,
                    },
                ),
                actor_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                recorded_at=assessment.assessed_at,
            )
        )

    def _outbox_warning(
        self, uow: ContactUnitOfWorkPort, actor: ActorContext, warning: Warning
    ) -> None:
        now = self._clock.now_utc()
        event = EventEnvelope(
            event_id=self._id_generator.new_id(),
            event_type="warning.dispatched",
            aggregate_id=warning.warning_id,
            aggregate_revision=warning.revision,
            occurred_at=now,
            correlation_id=warning.assessment_id,
            execution_mode=actor.execution_mode,
            payload={"assessment_id": str(warning.assessment_id)},
        )
        uow.audit.append(
            AuditRecord(
                event=event,
                actor_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                recorded_at=now,
            )
        )
        uow.outbox.add(
            OutboxMessage(
                message_id=self._id_generator.new_id(),
                event=event,
                topic="in_app.warning",
                state=OutboxState.PENDING,
                attempts=0,
                next_attempt_at=now,
                lease_expires_at=None,
                delivered_at=None,
                last_error_code=None,
                revision=0,
                created_at=now,
            )
        )


def _owned(incident: Incident, actor: ActorContext) -> bool:
    return (
        incident.owner_id == actor.user_id
        and incident.namespace_id == actor.namespace_id
        and incident.execution_mode is actor.execution_mode
    )


def _reassessment_scope(actor: ActorContext, key: str) -> IdempotencyScope:
    return IdempotencyScope(
        principal_fingerprint=canonical_sha256({"actor_id": str(actor.user_id)}),
        session_id=actor.session_id,
        namespace_id=actor.namespace_id,
        method="POST",
        canonical_route="/api/v1/observations/{observation_id}/reassess",
        key=key,
    )


def _owned_assessment(assessment: RiskAssessment, actor: ActorContext) -> bool:
    return (
        assessment.owner_id == actor.user_id
        and assessment.namespace_id == actor.namespace_id
        and assessment.provenance.execution_mode is actor.execution_mode
    )


def _analysis_input(observation: ObservationView, context_version: int) -> ObservationAnalysisInput:
    payload = observation.payload
    text: str | None = None
    raw_url: str | None = None
    if isinstance(payload, (SmsPayload, MessengerPayload)):
        text = payload.text
    elif isinstance(payload, CallTranscriptPayload):
        text = payload.transcript
    elif isinstance(payload, WebResourcePayload):
        raw_url = payload.url
    normalized = tuple(
        item
        for item in observation.normalized_indicators
        if item.status is NormalizationStatus.NORMALIZED
    )
    normalized_url = next(
        (
            item.normalized_value
            for item in normalized
            if item.indicator_type is CommunicationIndicatorType.URL
        ),
        None,
    )
    return ObservationAnalysisInput(
        observation_id=observation.observation_id,
        owner_id=observation.owner_id,
        session_id=observation.session_id,
        namespace_id=observation.namespace_id,
        kind=observation.kind,
        text=text,
        raw_resource_url=raw_url,
        normalized_resource_url=normalized_url if raw_url is not None else None,
        normalized_indicators=normalized,
        media_refs=observation.media_refs,
        context_version=context_version,
        execution_mode=observation.execution_mode,
    )
