"""Domain acceptance tests for deterministic P11 risk policy."""

from __future__ import annotations

from itertools import permutations

import pytest

from alpha_defense.domain.detection import (
    AnalysisApplicability,
    AnalysisPlan,
    AnalysisRequirement,
    AnalysisResult,
    AnalysisStatus,
    AnalyzerKind,
    AssessmentCompleteness,
    LinkedContactContext,
    RiskPolicy,
    RiskThresholds,
    Signal,
    SignalPolicyDefinition,
)
from alpha_defense.domain.shared import ExecutionMode, Provenance, Severity


def _policy() -> RiskPolicy:
    weights = {
        "urgency_or_secrecy": 15,
        "lookalike_domain": 45,
        "active_threat_match": 85,
        "new_recipient": 15,
        "new_recipient_amount_outlier": 50,
    }
    return RiskPolicy(
        policy_version="test-v1",
        score_kind="heuristic",
        thresholds=RiskThresholds(24, 49, 79, 100),
        signals=tuple(
            SignalPolicyDefinition(
                code=code,
                group="social_engineering" if code == "urgency_or_secrecy" else "test",
                base_score=score,
            )
            for code, score in weights.items()
        ),
        urgency_with_other_signal=10,
        linked_contact=20,
        max_score=100,
    )


def _provenance() -> Provenance:
    return Provenance(ExecutionMode.MOCK, "test", "v1", "v1")


def _plan(*applicable: AnalyzerKind) -> AnalysisPlan:
    return AnalysisPlan(
        version="test-plan-v1",
        requirements=tuple(
            AnalysisRequirement(
                analyzer=analyzer,
                applicability=(
                    AnalysisApplicability.APPLICABLE
                    if analyzer in applicable
                    else AnalysisApplicability.NOT_APPLICABLE
                ),
                required=analyzer in applicable,
                reason_code=(
                    "analysis_required" if analyzer in applicable else "content_not_applicable"
                ),
            )
            for analyzer in (
                AnalyzerKind.TEXT,
                AnalyzerKind.RESOURCE_URL,
                AnalyzerKind.THREAT_LOOKUP,
                AnalyzerKind.RESOURCE_VISUAL,
            )
        ),
    )


def _result(
    analyzer: AnalyzerKind,
    status: AnalysisStatus,
    *signals: Signal,
    reason: str = "test_result",
) -> AnalysisResult:
    return AnalysisResult(
        analyzer=analyzer,
        status=status,
        signals=signals,
        reason_codes=(reason,),
        latency_ms=0,
        provenance=_provenance(),
    )


def _results(
    *,
    text_status: AnalysisStatus,
    text_signals: tuple[Signal, ...] = (),
    resource_status: AnalysisStatus = AnalysisStatus.NOT_APPLICABLE,
) -> tuple[AnalysisResult, ...]:
    return (
        _result(AnalyzerKind.TEXT, text_status, *text_signals),
        _result(AnalyzerKind.RESOURCE_URL, resource_status),
        _result(AnalyzerKind.THREAT_LOOKUP, AnalysisStatus.NOT_APPLICABLE),
        _result(AnalyzerKind.RESOURCE_VISUAL, AnalysisStatus.NOT_APPLICABLE),
    )


@pytest.mark.parametrize(
    ("score", "severity"),
    [
        (0, Severity.LOW),
        (24, Severity.LOW),
        (25, Severity.MEDIUM),
        (49, Severity.MEDIUM),
        (50, Severity.HIGH),
        (79, Severity.HIGH),
        (80, Severity.CRITICAL),
        (100, Severity.CRITICAL),
    ],
)
def test_severity_boundaries(score: int, severity: Severity) -> None:
    assert _policy().classify(score) is severity


def test_deduplication_absorption_modifiers_and_cap_are_deterministic() -> None:
    evidence_ref = "observation:1:text"
    original = (
        Signal("new_recipient", evidence_ref, 100, "z-source"),
        Signal("new_recipient_amount_outlier", evidence_ref, 100, "behavior"),
        Signal("active_threat_match", "synthetic://threat/1", 100, "registry"),
        Signal("urgency_or_secrecy", evidence_ref, 100, "text"),
        Signal("urgency_or_secrecy", evidence_ref, 90, "a-source"),
    )
    outcomes = [
        _policy().evaluate(
            plan=_plan(AnalyzerKind.TEXT),
            analyzer_results=_results(
                text_status=AnalysisStatus.OK,
                text_signals=tuple(items),
            ),
            linked_contact=LinkedContactContext(
                severity=Severity.HIGH,
                evidence_ref="incident:linked",
            ),
        )
        for items in permutations(original)
    ]

    assert len(set(outcomes)) == 1
    outcome = outcomes[0]
    assert outcome.score == 100
    assert outcome.severity is Severity.CRITICAL
    assert "new_recipient" not in {item.code for item in outcome.signals}
    assert [item.code for item in outcome.signals].count("urgency_or_secrecy") == 1
    assert {item.code for item in outcome.applied_modifiers} == {
        "linked_contact",
        "urgency_with_other_signal",
    }


def test_partial_unavailable_and_not_applicable_have_distinct_semantics() -> None:
    signal = Signal("urgency_or_secrecy", "observation:1:text", 100, "text")
    partial = _policy().evaluate(
        plan=_plan(AnalyzerKind.TEXT, AnalyzerKind.RESOURCE_URL),
        analyzer_results=_results(
            text_status=AnalysisStatus.OK,
            text_signals=(signal,),
            resource_status=AnalysisStatus.UNAVAILABLE,
        ),
    )
    unavailable = _policy().evaluate(
        plan=_plan(AnalyzerKind.TEXT),
        analyzer_results=_results(text_status=AnalysisStatus.UNAVAILABLE),
    )
    no_usable_analyzers = _policy().evaluate(
        plan=_plan(),
        analyzer_results=_results(text_status=AnalysisStatus.NOT_APPLICABLE),
    )

    assert partial.completeness is AssessmentCompleteness.PARTIAL
    assert partial.score == 15
    assert partial.severity is Severity.LOW
    assert "analysis_partial" in partial.reason_codes
    assert unavailable.completeness is AssessmentCompleteness.UNAVAILABLE
    assert unavailable.score is None
    assert unavailable.severity is Severity.UNKNOWN
    assert no_usable_analyzers.completeness is AssessmentCompleteness.UNAVAILABLE
    assert no_usable_analyzers.score is None
    assert "analysis_unavailable" in no_usable_analyzers.reason_codes
