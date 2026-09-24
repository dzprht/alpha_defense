# ruff: noqa: RUF001
"""M03 policy v2 keeps model evidence distinct and degrades honestly."""

from __future__ import annotations

import pytest
from tests.catalog_helpers import REPOSITORY_ROOT

from alpha_defense.application.detection.policy_mapping import risk_policy_from_snapshot
from alpha_defense.application.ports import TextAnalysisRequest
from alpha_defense.domain.detection import (
    AnalysisApplicability,
    AnalysisPlan,
    AnalysisRequirement,
    AnalysisResult,
    AnalysisStatus,
    AnalyzerKind,
    AssessmentCompleteness,
    Signal,
)
from alpha_defense.domain.education import GuidanceCompleteness, GuidancePolicy
from alpha_defense.domain.shared import ExecutionMode, Provenance, Severity
from alpha_defense.infrastructure.analysis.mock import DeterministicTextAnalyzer
from alpha_defense.infrastructure.content import LocalCatalogLoader


def _catalog() -> LocalCatalogLoader:
    return LocalCatalogLoader(
        schema_root=REPOSITORY_ROOT / "contracts/fixtures",
        content_root=REPOSITORY_ROOT / "content",
        fixture_root=REPOSITORY_ROOT / "fixtures",
        policy_version="demo-risk-v2",
    )


def _plan() -> AnalysisPlan:
    return AnalysisPlan(
        "observation-analysis-v2",
        (
            AnalysisRequirement(
                AnalyzerKind.TEXT, AnalysisApplicability.APPLICABLE, True, "analysis_required"
            ),
            AnalysisRequirement(
                AnalyzerKind.TEXT_MODEL, AnalysisApplicability.APPLICABLE, True, "analysis_required"
            ),
        ),
    )


def _model_result(*, score: float | None, unavailable: bool = False) -> AnalysisResult:
    return AnalysisResult(
        analyzer=AnalyzerKind.TEXT_MODEL,
        status=AnalysisStatus.UNAVAILABLE if unavailable else AnalysisStatus.OK,
        signals=(Signal("ml_suspicious_text", "observation:test:model", 80, "trained-text-model"),)
        if score is not None and score >= 0.5
        else (),
        reason_codes=("ml_model_failure",) if unavailable else ("ml_text_scored",),
        latency_ms=1,
        provenance=Provenance(
            ExecutionMode.MOCK, "trained-text-model", "text-tfidf-logreg-v1", "a" * 64
        ),
        model_score=score,
    )


def _rules(text: str) -> AnalysisResult:
    return DeterministicTextAnalyzer().analyze(
        TextAnalysisRequest(text, "observation:test:text", ExecutionMode.MOCK)
    )


def test_v2_policy_uses_separate_model_signal_without_relabeling_rules() -> None:
    catalog = _catalog().load()
    policy = risk_policy_from_snapshot(catalog.policy)
    result = policy.evaluate(
        plan=_plan(),
        analyzer_results=(_rules("Напоминаю о встрече завтра утром"), _model_result(score=0.8)),
    )
    assert catalog.policy.policy_version == "demo-risk-v2"
    assert result.completeness is AssessmentCompleteness.COMPLETE
    assert result.severity is Severity.HIGH
    assert result.score == 55
    assert {signal.code for signal in result.signals} == {"ml_suspicious_text"}
    assert result.reason_codes == ("ml_suspicious_text",)

    guidance = _catalog().load_guidance("ru-RU")
    selection = GuidancePolicy().select(
        catalog=guidance,
        severity=result.severity,
        completeness=GuidanceCompleteness.COMPLETE,
        reason_codes=result.reason_codes,
    )
    assert selection.unmapped_reason_codes == ()
    assert any(item.code == "model_text_warning" for item in selection.recommendations)
    assert "сходство" in next(
        item.body for item in selection.recommendations if item.code == "model_text_warning"
    )


def test_model_failure_with_no_strong_rule_is_unknown_partial() -> None:
    policy = risk_policy_from_snapshot(_catalog().load_policy())
    outcome = policy.evaluate(
        plan=_plan(),
        analyzer_results=(
            _rules("Напоминаю о встрече завтра утром"),
            _model_result(score=None, unavailable=True),
        ),
    )
    assert outcome.completeness is AssessmentCompleteness.PARTIAL
    assert outcome.severity is Severity.UNKNOWN
    assert outcome.score is None
    assert "analysis_partial" in outcome.reason_codes
    assert "ml_model_failure" in outcome.reason_codes


def test_model_failure_preserves_strong_rule_evidence_but_is_partial() -> None:
    policy = risk_policy_from_snapshot(_catalog().load_policy())
    outcome = policy.evaluate(
        plan=_plan(),
        analyzer_results=(
            _rules("Назовите пароль от личного кабинета"),
            _model_result(score=None, unavailable=True),
        ),
    )
    assert outcome.completeness is AssessmentCompleteness.PARTIAL
    assert outcome.severity is Severity.HIGH
    assert outcome.score == 55
    assert "credential_request" in outcome.reason_codes
    assert "ml_model_failure" in outcome.reason_codes


def test_model_score_cannot_be_reused_as_a_rule_score() -> None:
    with pytest.raises(ValueError, match="model_score"):
        AnalysisResult(
            analyzer=AnalyzerKind.TEXT,
            status=AnalysisStatus.OK,
            signals=(),
            reason_codes=(),
            latency_ms=0,
            provenance=Provenance(ExecutionMode.MOCK, "rules", "v1", "v1"),
            model_score=0.8,
        )
