"""Bootstrap integration of S01 observation, registry evidence, and P11 policy."""

from __future__ import annotations

from pathlib import Path

from alpha_defense.application.communications import ObservationInput, SmsPayload
from alpha_defense.application.detection import (
    ObservationAnalysisInput,
    ThreatEvidenceOutcome,
    ThreatLookupEvidence,
)
from alpha_defense.application.threats import ThreatLookupOutcome
from alpha_defense.bootstrap import build_container
from alpha_defense.domain.communications import NormalizationStatus
from alpha_defense.domain.detection import AssessmentCompleteness
from alpha_defense.domain.shared import Severity
from alpha_defense.domain.threats import IndicatorType, ThreatIndicator
from alpha_defense.transport.http.v1.schemas import ObservationInputSchema
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def test_s01_catalog_registry_and_analysis_compose_without_answer_labels(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "app.db"
    migrate(database_path)
    container = build_container(make_settings(tmp_path))
    bootstrap = container.identity_service.bootstrap_session(
        session_token=None,
        pre_session_token=None,
    )
    assert bootstrap.pre_session_token is not None
    started = container.identity_service.start_session(
        pre_session_token=bootstrap.pre_session_token,
        idempotency_key="start-p11-session",
        profile_code="demo-user",
    )
    actor = container.identity_service.resolve_actor(started.session_token)
    fixture = next(
        item
        for item in container.catalog.load().fixtures
        if item.fixture_id == "s01-card-block-sms"
    )
    request = dict(fixture.payload)
    source = request.pop("source")
    assert isinstance(source, str)
    observation_input: ObservationInput = ObservationInputSchema.model_validate(request).to_input()
    assert isinstance(observation_input.payload, SmsPayload)
    created = container.analyze_contact.execute(
        actor=actor,
        source=source,
        observation_input=observation_input,
    )
    normalized = tuple(
        item
        for item in created.observation.normalized_indicators
        if item.status is NormalizationStatus.NORMALIZED
    )
    threat_indicators = tuple(
        ThreatIndicator(
            indicator_type=IndicatorType(item.indicator_type.value),
            normalized_value=item.normalized_value,
        )
        for item in normalized
        if item.normalized_value is not None
    )
    container.refresh_threat_registry.execute()
    lookups = container.lookup_threats.execute(threat_indicators)
    matched = tuple(item for item in lookups if item.outcome is ThreatLookupOutcome.MATCH)
    assert matched
    threat_evidence = ThreatLookupEvidence(
        outcome=ThreatEvidenceOutcome.MATCH,
        evidence_refs=tuple(
            sorted({match.evidence_ref for item in matched for match in item.matches})
        ),
        snapshot_version=matched[0].snapshot_version,
        reason_code="active_exact_match",
    )

    assessment = container.assess_observation.execute(
        actor=actor,
        observation=ObservationAnalysisInput(
            observation_id=created.observation.observation_id,
            owner_id=created.observation.owner_id,
            session_id=created.observation.session_id,
            namespace_id=created.observation.namespace_id,
            kind=created.observation.kind,
            text=observation_input.payload.text,
            raw_resource_url=None,
            normalized_resource_url=None,
            normalized_indicators=normalized,
            media_refs=created.observation.media_refs,
            context_version=created.incident.context_version,
            execution_mode=created.observation.execution_mode,
        ),
        threat_evidence=threat_evidence,
    )
    container.close()

    assert assessment.severity is Severity.CRITICAL
    assert assessment.score == 95
    assert assessment.completeness is AssessmentCompleteness.COMPLETE
    assert assessment.context_version == created.incident.context_version
    assert "active_threat_match" in assessment.reason_codes
    assert assessment.has_mock_evidence
