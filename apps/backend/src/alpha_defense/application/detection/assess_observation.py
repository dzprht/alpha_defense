"""Assess one observation with an explicit plan and immutable evidence."""

from __future__ import annotations

from alpha_defense.application.detection.dto import (
    ObservationAnalysisInput,
    ThreatEvidenceOutcome,
    ThreatLookupEvidence,
)
from alpha_defense.application.detection.plan import build_observation_analysis_plan
from alpha_defense.application.detection.policy_mapping import risk_policy_from_snapshot
from alpha_defense.application.ports import (
    CatalogLoaderPort,
    Clock,
    IdGenerator,
    ResourceAnalysisPort,
    ResourceAnalysisRequest,
    TextAnalysisPort,
    TextAnalysisRequest,
    TextModelAnalysisPort,
)
from alpha_defense.application.shared import ActorContext, ResourceNotFoundError
from alpha_defense.domain.detection import (
    AnalysisApplicability,
    AnalysisPlan,
    AnalysisResult,
    AnalysisStatus,
    AnalyzerKind,
    AssessmentTargetKind,
    RiskAssessment,
    Signal,
)
from alpha_defense.domain.shared import ExecutionMode, Provenance


class AssessObservation:
    def __init__(
        self,
        *,
        catalog: CatalogLoaderPort,
        text_analyzer: TextAnalysisPort,
        text_model_analyzer: TextModelAnalysisPort | None = None,
        resource_analyzer: ResourceAnalysisPort,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._catalog = catalog
        self._text_analyzer = text_analyzer
        self._text_model_analyzer = text_model_analyzer
        self._resource_analyzer = resource_analyzer
        self._clock = clock
        self._id_generator = id_generator

    def execute(
        self,
        *,
        actor: ActorContext,
        observation: ObservationAnalysisInput,
        threat_evidence: ThreatLookupEvidence | None = None,
    ) -> RiskAssessment:
        _require_actor_scope(actor, observation)
        catalog = self._catalog.load()
        if catalog.policy.policy_version == "demo-risk-v2" and self._text_model_analyzer is None:
            raise ValueError("model-enabled policy requires a text model analyzer")
        plan = build_observation_analysis_plan(
            observation, include_text_model=self._text_model_analyzer is not None
        )
        trusted_domains = tuple(
            item.value
            for item in catalog.trusted_entities.entities
            if item.kind == "domain" and item.status == "trusted"
        )
        trusted_brands = tuple(
            item.value
            for item in catalog.trusted_entities.entities
            if item.kind == "brand" and item.status == "trusted"
        )
        results = tuple(
            self._run_analyzer(
                analyzer=requirement.analyzer,
                plan=plan,
                observation=observation,
                threat_evidence=threat_evidence,
                trusted_domains=trusted_domains,
                trusted_brands=trusted_brands,
                catalog_version=catalog.trusted_entities.catalog_version,
            )
            for requirement in plan.requirements
        )
        for result in results:
            if result.provenance.execution_mode is not observation.execution_mode:
                raise ValueError("analyzer result execution mode does not match observation")
        policy = risk_policy_from_snapshot(catalog.policy)
        outcome = policy.evaluate(plan=plan, analyzer_results=results)
        assessment_provenance = Provenance(
            execution_mode=observation.execution_mode,
            provider="alpha-defense-risk-policy",
            provider_version=catalog.policy.policy_version,
            data_version=catalog.policy.content_sha256,
        )
        return RiskAssessment(
            assessment_id=self._id_generator.new_id(),
            owner_id=observation.owner_id,
            session_id=observation.session_id,
            namespace_id=observation.namespace_id,
            target_kind=AssessmentTargetKind.OBSERVATION,
            target_id=observation.observation_id,
            severity=outcome.severity,
            score=outcome.score,
            score_kind=policy.score_kind,
            completeness=outcome.completeness,
            signals=outcome.signals,
            applied_modifiers=outcome.applied_modifiers,
            reason_codes=outcome.reason_codes,
            analyzer_results=results,
            policy_version=policy.policy_version,
            analysis_plan_version=plan.version,
            assessed_at=self._clock.now_utc(),
            context_version=observation.context_version,
            provenance=assessment_provenance,
            has_mock_evidence=observation.execution_mode is ExecutionMode.MOCK,
        )

    def _run_analyzer(
        self,
        *,
        analyzer: AnalyzerKind,
        plan: AnalysisPlan,
        observation: ObservationAnalysisInput,
        threat_evidence: ThreatLookupEvidence | None,
        trusted_domains: tuple[str, ...],
        trusted_brands: tuple[str, ...],
        catalog_version: str,
    ) -> AnalysisResult:
        requirement = plan.requirement_for(analyzer)
        if requirement.applicability is AnalysisApplicability.NOT_APPLICABLE:
            return _plan_result(
                analyzer=analyzer,
                status=AnalysisStatus.NOT_APPLICABLE,
                reason_code=requirement.reason_code,
                mode=observation.execution_mode,
                plan_version=plan.version,
            )
        evidence_ref = f"observation:{observation.observation_id}:{analyzer.value}"
        if analyzer is AnalyzerKind.TEXT:
            assert observation.text is not None
            return self._text_analyzer.analyze(
                TextAnalysisRequest(
                    text=observation.text,
                    evidence_ref=evidence_ref,
                    execution_mode=observation.execution_mode,
                )
            )
        if analyzer is AnalyzerKind.TEXT_MODEL:
            assert observation.text is not None
            assert self._text_model_analyzer is not None
            return self._text_model_analyzer.analyze(
                TextAnalysisRequest(
                    text=observation.text,
                    evidence_ref=evidence_ref,
                    execution_mode=observation.execution_mode,
                )
            )
        if analyzer is AnalyzerKind.RESOURCE_URL:
            if observation.normalized_resource_url is None:
                return _plan_result(
                    analyzer=analyzer,
                    status=AnalysisStatus.INSUFFICIENT_DATA,
                    reason_code="resource_url_invalid",
                    mode=observation.execution_mode,
                    plan_version=plan.version,
                )
            return self._resource_analyzer.analyze(
                ResourceAnalysisRequest(
                    normalized_url=observation.normalized_resource_url,
                    evidence_ref=evidence_ref,
                    trusted_domains=trusted_domains,
                    trusted_brand_names=trusted_brands,
                    trusted_catalog_version=catalog_version,
                    execution_mode=observation.execution_mode,
                )
            )
        if analyzer is AnalyzerKind.THREAT_LOOKUP:
            return _threat_result(
                evidence=threat_evidence,
                mode=observation.execution_mode,
                plan_version=plan.version,
            )
        return _plan_result(
            analyzer=analyzer,
            status=AnalysisStatus.UNAVAILABLE,
            reason_code="visual_analyzer_not_configured",
            mode=observation.execution_mode,
            plan_version=plan.version,
        )


def _threat_result(
    *,
    evidence: ThreatLookupEvidence | None,
    mode: ExecutionMode,
    plan_version: str,
) -> AnalysisResult:
    if evidence is None:
        return _plan_result(
            analyzer=AnalyzerKind.THREAT_LOOKUP,
            status=AnalysisStatus.UNAVAILABLE,
            reason_code="threat_evidence_not_supplied",
            mode=mode,
            plan_version=plan_version,
        )
    data_version = evidence.snapshot_version or "unavailable"
    provenance = Provenance(
        execution_mode=mode,
        provider="threat-registry",
        provider_version="exact-match-v1",
        data_version=data_version,
    )
    if evidence.outcome is ThreatEvidenceOutcome.UNAVAILABLE:
        return AnalysisResult(
            analyzer=AnalyzerKind.THREAT_LOOKUP,
            status=AnalysisStatus.UNAVAILABLE,
            signals=(),
            reason_codes=(evidence.reason_code,),
            latency_ms=0,
            provenance=provenance,
        )
    signals = (
        tuple(
            Signal(
                code="active_threat_match",
                evidence_ref=evidence_ref,
                strength=100,
                source="threat-registry",
            )
            for evidence_ref in evidence.evidence_refs
        )
        if evidence.outcome is ThreatEvidenceOutcome.MATCH
        else ()
    )
    return AnalysisResult(
        analyzer=AnalyzerKind.THREAT_LOOKUP,
        status=AnalysisStatus.OK,
        signals=signals,
        reason_codes=(evidence.reason_code,),
        latency_ms=0,
        provenance=provenance,
    )


def _plan_result(
    *,
    analyzer: AnalyzerKind,
    status: AnalysisStatus,
    reason_code: str,
    mode: ExecutionMode,
    plan_version: str,
) -> AnalysisResult:
    return AnalysisResult(
        analyzer=analyzer,
        status=status,
        signals=(),
        reason_codes=(reason_code,),
        latency_ms=0,
        provenance=Provenance(
            execution_mode=mode,
            provider="analysis-plan",
            provider_version=plan_version,
            data_version=plan_version,
        ),
    )


def _require_actor_scope(
    actor: ActorContext,
    observation: ObservationAnalysisInput,
) -> None:
    if (
        observation.owner_id != actor.user_id
        or observation.namespace_id != actor.namespace_id
        or observation.execution_mode is not actor.execution_mode
    ):
        raise ResourceNotFoundError("Наблюдение не найдено.")
