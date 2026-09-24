"""Deterministic domain policy for explainable heuristic risk scoring."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_defense.domain.detection.assessment import (
    AppliedRiskModifier,
    AssessmentCompleteness,
)
from alpha_defense.domain.detection.signal import (
    AnalysisApplicability,
    AnalysisPlan,
    AnalysisResult,
    AnalysisStatus,
    AnalyzerKind,
    Signal,
)
from alpha_defense.domain.shared import Severity


@dataclass(frozen=True, slots=True)
class RiskThresholds:
    low_max: int
    medium_max: int
    high_max: int
    critical_max: int

    def __post_init__(self) -> None:
        values = (self.low_max, self.medium_max, self.high_max, self.critical_max)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError("risk thresholds must be integers")
        if not 0 <= self.low_max < self.medium_max < self.high_max < self.critical_max:
            raise ValueError("risk thresholds must be strictly increasing")


@dataclass(frozen=True, slots=True)
class SignalPolicyDefinition:
    code: str
    group: str
    base_score: int

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("signal policy code must be non-empty")
        if not isinstance(self.group, str) or not self.group:
            raise ValueError("signal policy group must be non-empty")
        if isinstance(self.base_score, bool) or not isinstance(self.base_score, int):
            raise TypeError("base_score must be an integer")
        if not 0 <= self.base_score <= 100:
            raise ValueError("base_score must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class LinkedContactContext:
    severity: Severity
    evidence_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be a Severity")
        if not isinstance(self.evidence_ref, str) or not self.evidence_ref:
            raise ValueError("evidence_ref must be non-empty")


@dataclass(frozen=True, slots=True)
class RiskPolicyOutcome:
    severity: Severity
    score: int | None
    completeness: AssessmentCompleteness
    signals: tuple[Signal, ...]
    applied_modifiers: tuple[AppliedRiskModifier, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    policy_version: str
    score_kind: str
    thresholds: RiskThresholds
    signals: tuple[SignalPolicyDefinition, ...]
    urgency_with_other_signal: int
    linked_contact: int
    max_score: int
    incomplete_low_is_unknown: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version:
            raise ValueError("policy_version must be non-empty")
        if self.score_kind != "heuristic":
            raise ValueError("only heuristic score_kind is supported")
        if not isinstance(self.thresholds, RiskThresholds):
            raise TypeError("thresholds must be RiskThresholds")
        if not isinstance(self.signals, tuple) or any(
            not isinstance(item, SignalPolicyDefinition) for item in self.signals
        ):
            raise TypeError("signals must contain SignalPolicyDefinition values")
        codes = tuple(item.code for item in self.signals)
        if len(set(codes)) != len(codes):
            raise ValueError("signal policy codes must be unique")
        for field_name in ("urgency_with_other_signal", "linked_contact", "max_score"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
            if not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between 0 and 100")
        if self.max_score != self.thresholds.critical_max:
            raise ValueError("max_score must equal critical_max")
        if not isinstance(self.incomplete_low_is_unknown, bool):
            raise TypeError("incomplete_low_is_unknown must be a boolean")

    def evaluate(
        self,
        *,
        plan: AnalysisPlan,
        analyzer_results: tuple[AnalysisResult, ...],
        linked_contact: LinkedContactContext | None = None,
    ) -> RiskPolicyOutcome:
        completeness = _completeness(plan, analyzer_results)
        failure_reasons = _failure_reasons(plan, analyzer_results)
        if completeness is AssessmentCompleteness.UNAVAILABLE:
            return RiskPolicyOutcome(
                severity=Severity.UNKNOWN,
                score=None,
                completeness=completeness,
                signals=(),
                applied_modifiers=(),
                reason_codes=_unique(("analysis_unavailable", *failure_reasons)),
            )

        successful_signals = tuple(
            signal
            for result in analyzer_results
            if result.status is AnalysisStatus.OK
            for signal in result.signals
        )
        effective_signals = self._effective_signals(successful_signals)
        policies = {item.code: item for item in self.signals}
        unknown_codes = {item.code for item in effective_signals} - policies.keys()
        if unknown_codes:
            raise ValueError(f"signals are absent from policy: {sorted(unknown_codes)}")

        ranked = sorted(
            effective_signals,
            key=lambda item: (-policies[item.code].base_score, item.code, item.evidence_ref),
        )
        score = 0 if not ranked else policies[ranked[0].code].base_score
        modifiers: list[AppliedRiskModifier] = []
        urgency = next(
            (item for item in effective_signals if item.code == "urgency_or_secrecy"),
            None,
        )
        base_signal = ranked[0] if ranked else None
        if (
            urgency is not None
            and base_signal is not None
            and policies[base_signal.code].group != policies[urgency.code].group
        ):
            modifiers.append(
                AppliedRiskModifier(
                    code="urgency_with_other_signal",
                    score_delta=self.urgency_with_other_signal,
                    evidence_ref=urgency.evidence_ref,
                )
            )
        if linked_contact is not None and linked_contact.severity in {
            Severity.MEDIUM,
            Severity.HIGH,
            Severity.CRITICAL,
        }:
            modifiers.append(
                AppliedRiskModifier(
                    code="linked_contact",
                    score_delta=self.linked_contact,
                    evidence_ref=linked_contact.evidence_ref,
                )
            )
        score = min(self.max_score, score + sum(item.score_delta for item in modifiers))
        signal_reasons = tuple(item.code for item in ranked)
        completeness_reasons = (
            ("analysis_partial", *failure_reasons)
            if completeness is AssessmentCompleteness.PARTIAL
            else ()
        )
        incomplete_without_strong_signal = (
            self.incomplete_low_is_unknown
            and completeness is AssessmentCompleteness.PARTIAL
            and score <= self.thresholds.medium_max
        )
        return RiskPolicyOutcome(
            severity=Severity.UNKNOWN if incomplete_without_strong_signal else self.classify(score),
            score=None if incomplete_without_strong_signal else score,
            completeness=completeness,
            signals=effective_signals,
            applied_modifiers=tuple(modifiers),
            reason_codes=_unique((*signal_reasons, *completeness_reasons)),
        )

    def classify(self, score: int) -> Severity:
        if isinstance(score, bool) or not isinstance(score, int):
            raise TypeError("score must be an integer")
        if not 0 <= score <= self.max_score:
            raise ValueError("score is outside policy bounds")
        if score <= self.thresholds.low_max:
            return Severity.LOW
        if score <= self.thresholds.medium_max:
            return Severity.MEDIUM
        if score <= self.thresholds.high_max:
            return Severity.HIGH
        return Severity.CRITICAL

    def _effective_signals(self, signals: tuple[Signal, ...]) -> tuple[Signal, ...]:
        unique: dict[tuple[str, str], Signal] = {}
        for item in sorted(
            signals,
            key=lambda value: (
                value.code,
                value.evidence_ref,
                value.source,
                -value.strength,
            ),
        ):
            if item.applicability is AnalysisApplicability.APPLICABLE:
                unique.setdefault((item.code, item.evidence_ref), item)
        for code, evidence_ref in tuple(unique):
            if code == "new_recipient_amount_outlier":
                unique.pop(("new_recipient", evidence_ref), None)
        return tuple(
            sorted(
                unique.values(),
                key=lambda item: (item.code, item.evidence_ref, item.source),
            )
        )


def _completeness(
    plan: AnalysisPlan,
    results: tuple[AnalysisResult, ...],
) -> AssessmentCompleteness:
    by_analyzer = _validate_results(plan, results)
    applicable = tuple(
        requirement
        for requirement in plan.requirements
        if requirement.applicability is AnalysisApplicability.APPLICABLE
    )
    if not applicable:
        return AssessmentCompleteness.UNAVAILABLE
    successful = tuple(
        item for item in applicable if by_analyzer[item.analyzer].status is AnalysisStatus.OK
    )
    if not successful:
        return AssessmentCompleteness.UNAVAILABLE
    if len(successful) != len(applicable):
        return AssessmentCompleteness.PARTIAL
    return AssessmentCompleteness.COMPLETE


def _validate_results(
    plan: AnalysisPlan,
    results: tuple[AnalysisResult, ...],
) -> dict[AnalyzerKind, AnalysisResult]:
    if not isinstance(results, tuple) or any(
        not isinstance(item, AnalysisResult) for item in results
    ):
        raise TypeError("analyzer_results must contain AnalysisResult values")
    by_analyzer = {item.analyzer: item for item in results}
    if len(by_analyzer) != len(results):
        raise ValueError("analyzer results must be unique")
    planned = {item.analyzer for item in plan.requirements}
    if set(by_analyzer) != planned:
        raise ValueError("analyzer results must exactly match the analysis plan")
    for requirement in plan.requirements:
        status = by_analyzer[requirement.analyzer].status
        if requirement.applicability is AnalysisApplicability.NOT_APPLICABLE:
            if status is not AnalysisStatus.NOT_APPLICABLE:
                raise ValueError("non-applicable analyzer must return not_applicable")
        elif status is AnalysisStatus.NOT_APPLICABLE:
            raise ValueError("applicable analyzer cannot return not_applicable")
    return by_analyzer


def _failure_reasons(
    plan: AnalysisPlan,
    results: tuple[AnalysisResult, ...],
) -> tuple[str, ...]:
    by_analyzer = _validate_results(plan, results)
    reasons: list[str] = []
    for requirement in plan.requirements:
        result = by_analyzer[requirement.analyzer]
        if (
            requirement.applicability is AnalysisApplicability.APPLICABLE
            and result.status is not AnalysisStatus.OK
        ):
            reasons.extend(
                result.reason_codes or (f"{result.analyzer.value}_{result.status.value}",)
            )
    return _unique(tuple(reasons))


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
