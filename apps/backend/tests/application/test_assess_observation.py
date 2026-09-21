"""Application acceptance tests for the P11 observation assessment boundary."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from uuid import UUID

import pytest
from tests.contract.test_uow_contract import FixedIdGenerator, FrozenClock

from alpha_defense.application.detection import (
    AssessObservation,
    ObservationAnalysisInput,
    ThreatEvidenceOutcome,
    ThreatLookupEvidence,
)
from alpha_defense.application.ports import (
    CatalogSnapshot,
    PolicySnapshot,
    RiskThresholds,
    SignalPolicy,
    TrustedEntitiesSnapshot,
    TrustedEntity,
)
from alpha_defense.application.shared import ActorContext, ActorRole, ResourceNotFoundError
from alpha_defense.domain.communications import (
    NormalizationStatus,
    ObservationKind,
    indicators_from_resource,
    indicators_from_text,
)
from alpha_defense.domain.detection import AssessmentCompleteness
from alpha_defense.domain.shared import EntityId, ExecutionMode, Severity
from alpha_defense.infrastructure.analysis.mock import (
    DeterministicTextAnalyzer,
    DeterministicUrlAnalyzer,
)

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


class StaticCatalog:
    def __init__(self, value: CatalogSnapshot) -> None:
        self._value = value

    def load(self) -> CatalogSnapshot:
        return self._value


def _id(value: int) -> EntityId:
    return EntityId(UUID(int=value))


DEFAULT_OWNER_ID = _id(1)


def _actor(*, owner_id: EntityId = DEFAULT_OWNER_ID) -> ActorContext:
    return ActorContext(
        user_id=owner_id,
        session_id=_id(2),
        namespace_id=_id(3),
        roles=frozenset({ActorRole.DEMO_USER}),
        consent_revision=0,
        execution_mode=ExecutionMode.MOCK,
    )


def _catalog() -> CatalogSnapshot:
    definitions = {
        "urgency_or_secrecy": ("social_engineering", 15),
        "prize_fee_request": ("payment_request", 30),
        "delivery_fee_request": ("payment_request", 30),
        "relative_emergency_payment": ("payment_request", 45),
        "lookalike_domain": ("resource", 45),
        "credential_request": ("credentials", 55),
        "visual_brand_imitation": ("resource", 55),
        "safe_account_transfer": ("payment_request", 60),
        "active_threat_match": ("threat_intelligence", 85),
        "new_recipient": ("behavior", 15),
        "known_recipient_amount_outlier": ("behavior", 30),
        "new_recipient_amount_outlier": ("behavior", 50),
        "active_fraud_network_link": ("network", 80),
    }
    return CatalogSnapshot(
        policy=PolicySnapshot(
            schema_version="1.0",
            policy_version="demo-risk-v1",
            score_kind="heuristic",
            thresholds=RiskThresholds(24, 49, 79, 100),
            signals=tuple(
                SignalPolicy(code=code, group=group, base_score=score)
                for code, (group, score) in definitions.items()
            ),
            urgency_with_other_signal=10,
            linked_contact=20,
            deduplication_key="code+evidence_ref",
            max_score=100,
            content_sha256="a" * 64,
        ),
        trusted_entities=TrustedEntitiesSnapshot(
            schema_version="1.0",
            catalog_version="trusted-v1",
            source="synthetic",
            reviewed_at=NOW,
            entities=(
                TrustedEntity("brand", "brand", "Альфа-Банк", "trusted"),
                TrustedEntity("domain", "domain", "alfabank.ru", "trusted"),
            ),
            content_sha256="b" * 64,
        ),
        fixtures=(),
        catalog_sha256="c" * 64,
    )


def _service() -> AssessObservation:
    return AssessObservation(
        catalog=StaticCatalog(_catalog()),
        text_analyzer=DeterministicTextAnalyzer(),
        resource_analyzer=DeterministicUrlAnalyzer(),
        clock=FrozenClock(NOW),
        id_generator=FixedIdGenerator(_id(100)),
    )


def _text_input(text: str) -> ObservationAnalysisInput:
    indicators = tuple(
        item
        for item in indicators_from_text(text, sender="UNKNOWN")
        if item.status is NormalizationStatus.NORMALIZED
    )
    return ObservationAnalysisInput(
        observation_id=_id(10),
        owner_id=_id(1),
        session_id=_id(2),
        namespace_id=_id(3),
        kind=ObservationKind.SMS,
        text=text,
        raw_resource_url=None,
        normalized_resource_url=None,
        normalized_indicators=indicators,
        media_refs=(),
        context_version=1,
        execution_mode=ExecutionMode.MOCK,
    )


def test_s01_text_and_verified_threat_evidence_produce_explainable_critical_result() -> None:
    observation = _text_input(
        "Ваша карта заблокирована. Срочно подтвердите данные по ссылке: "
        "https://alfa-secure-check.test/card"
    )
    threat = ThreatLookupEvidence(
        outcome=ThreatEvidenceOutcome.MATCH,
        evidence_refs=("synthetic://threats/s01-phishing-url",),
        snapshot_version="fixture-v1",
        reason_code="active_exact_match",
    )

    assessment = _service().execute(
        actor=_actor(),
        observation=observation,
        threat_evidence=threat,
    )

    assert assessment.severity is Severity.CRITICAL
    assert assessment.score == 95
    assert assessment.completeness is AssessmentCompleteness.COMPLETE
    assert {item.code for item in assessment.signals} == {
        "active_threat_match",
        "credential_request",
        "urgency_or_secrecy",
    }
    assert assessment.has_mock_evidence
    assert assessment.policy_version == "demo-risk-v1"


def test_missing_applicable_lookup_is_partial_not_safe() -> None:
    observation = _text_input(
        "Срочно подтвердите данные по ссылке: https://alfa-secure-check.test/card"
    )

    assessment = _service().execute(actor=_actor(), observation=observation)

    assert assessment.completeness is AssessmentCompleteness.PARTIAL
    assert assessment.severity is Severity.HIGH
    assert assessment.score == 65
    assert "threat_evidence_not_supplied" in assessment.reason_codes


def test_trusted_url_and_verified_no_match_add_no_risk_score() -> None:
    raw_url = "https://online.alfabank.ru/"
    indicators = indicators_from_resource(raw_url)
    normalized_url = next(
        item.normalized_value for item in indicators if item.indicator_type.value == "url"
    )
    assert normalized_url is not None
    observation = ObservationAnalysisInput(
        observation_id=_id(10),
        owner_id=_id(1),
        session_id=_id(2),
        namespace_id=_id(3),
        kind=ObservationKind.WEB_RESOURCE,
        text=None,
        raw_resource_url=raw_url,
        normalized_resource_url=normalized_url,
        normalized_indicators=indicators,
        media_refs=(),
        context_version=1,
        execution_mode=ExecutionMode.MOCK,
    )
    no_match = ThreatLookupEvidence(
        outcome=ThreatEvidenceOutcome.NO_MATCH,
        evidence_refs=(),
        snapshot_version="fixture-v1",
        reason_code="no_active_match",
    )

    assessment = _service().execute(
        actor=_actor(),
        observation=observation,
        threat_evidence=no_match,
    )

    assert assessment.completeness is AssessmentCompleteness.COMPLETE
    assert assessment.severity is Severity.LOW
    assert assessment.score == 0
    assert assessment.signals == ()


def test_no_usable_analyzer_is_unknown_while_non_applicable_work_is_ignored() -> None:
    observation = ObservationAnalysisInput(
        observation_id=_id(10),
        owner_id=_id(1),
        session_id=_id(2),
        namespace_id=_id(3),
        kind=ObservationKind.WEB_RESOURCE,
        text=None,
        raw_resource_url=None,
        normalized_resource_url=None,
        normalized_indicators=(),
        media_refs=(_id(50),),
        context_version=1,
        execution_mode=ExecutionMode.MOCK,
    )

    assessment = _service().execute(actor=_actor(), observation=observation)

    assert assessment.completeness is AssessmentCompleteness.UNAVAILABLE
    assert assessment.severity is Severity.UNKNOWN
    assert assessment.score is None
    assert "visual_analyzer_not_configured" in assessment.reason_codes


def test_assessment_is_deterministic_and_has_no_scenario_answer_fields() -> None:
    metadata = _text_input("Обычное сообщение без риск-маркеров")
    risky = _text_input("Срочно переведите деньги на безопасный счет")
    service = _service()

    first = service.execute(actor=_actor(), observation=metadata)
    repeated = service.execute(actor=_actor(), observation=metadata)
    changed = service.execute(actor=_actor(), observation=risky)

    input_fields = {item.name for item in fields(ObservationAnalysisInput)}
    assert first == repeated
    assert first.score == 0
    assert changed.score == 70
    assert not input_fields.intersection({"scenario_id", "expected_severity", "expected_signals"})


def test_assessment_hides_cross_owner_observations() -> None:
    with pytest.raises(ResourceNotFoundError, match="Наблюдение не найдено"):
        _service().execute(
            actor=_actor(owner_id=_id(999)),
            observation=_text_input("Обычное сообщение"),
        )
