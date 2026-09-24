"""Immutable risk assessment and applied policy modifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from alpha_defense.domain.detection.signal import AnalysisResult, Signal
from alpha_defense.domain.shared import EntityId, ExecutionMode, Provenance, Severity

_STABLE_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class AssessmentCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class AssessmentTargetKind(StrEnum):
    OBSERVATION = "observation"
    TRANSFER = "transfer"


@dataclass(frozen=True, slots=True)
class AppliedRiskModifier:
    code: str
    score_delta: int
    evidence_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not _STABLE_CODE.fullmatch(self.code):
            raise ValueError("modifier code must use lower snake case")
        if isinstance(self.score_delta, bool) or not isinstance(self.score_delta, int):
            raise TypeError("score_delta must be an integer")
        if self.score_delta < 0:
            raise ValueError("score_delta must be non-negative")
        if (
            not isinstance(self.evidence_ref, str)
            or not self.evidence_ref
            or self.evidence_ref != self.evidence_ref.strip()
            or len(self.evidence_ref) > 512
        ):
            raise ValueError("modifier evidence_ref must be non-empty, trimmed, and bounded")


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    assessment_id: EntityId
    owner_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    target_kind: AssessmentTargetKind
    target_id: EntityId
    severity: Severity
    score: int | None
    score_kind: str
    completeness: AssessmentCompleteness
    signals: tuple[Signal, ...]
    applied_modifiers: tuple[AppliedRiskModifier, ...]
    reason_codes: tuple[str, ...]
    analyzer_results: tuple[AnalysisResult, ...]
    policy_version: str
    analysis_plan_version: str
    assessed_at: datetime
    context_version: int
    provenance: Provenance
    has_mock_evidence: bool

    def __post_init__(self) -> None:
        for field_name in (
            "assessment_id",
            "owner_id",
            "session_id",
            "namespace_id",
            "target_id",
        ):
            if not isinstance(getattr(self, field_name), EntityId):
                raise TypeError(f"{field_name} must be an EntityId")
        if not isinstance(self.target_kind, AssessmentTargetKind):
            raise TypeError("target_kind must be an AssessmentTargetKind")
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be a Severity")
        if not isinstance(self.completeness, AssessmentCompleteness):
            raise TypeError("completeness must be an AssessmentCompleteness")
        if self.completeness is AssessmentCompleteness.UNAVAILABLE:
            if self.severity is not Severity.UNKNOWN or self.score is not None:
                raise ValueError("unavailable assessments require unknown severity and no score")
        elif (self.severity is Severity.UNKNOWN) != (self.score is None):
            raise ValueError("severity and score must be known or unknown together")
        elif self.completeness is AssessmentCompleteness.COMPLETE and self.score is None:
            raise ValueError("complete assessments require a known severity and score")
        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, int):
                raise TypeError("score must be an integer or None")
            if not 0 <= self.score <= 100:
                raise ValueError("score must be between 0 and 100")
        if self.score_kind != "heuristic":
            raise ValueError("score_kind must be heuristic")
        _require_tuple(self.signals, Signal, "signals")
        _require_tuple(self.applied_modifiers, AppliedRiskModifier, "applied_modifiers")
        _require_tuple(self.analyzer_results, AnalysisResult, "analyzer_results")
        if len({item.analyzer for item in self.analyzer_results}) != len(self.analyzer_results):
            raise ValueError("analyzer results must be unique")
        if not isinstance(self.reason_codes, tuple) or len(set(self.reason_codes)) != len(
            self.reason_codes
        ):
            raise ValueError("reason_codes must be a unique tuple")
        if any(
            not isinstance(item, str) or not _STABLE_CODE.fullmatch(item)
            for item in self.reason_codes
        ):
            raise ValueError("reason_codes must use lower snake case")
        for field_name in ("policy_version", "analysis_plan_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{field_name} must be non-empty and trimmed")
        if not isinstance(self.assessed_at, datetime):
            raise TypeError("assessed_at must be a datetime")
        if self.assessed_at.tzinfo is None or self.assessed_at.utcoffset() != UTC.utcoffset(
            self.assessed_at
        ):
            raise ValueError("assessed_at must be UTC-aware")
        if isinstance(self.context_version, bool) or not isinstance(self.context_version, int):
            raise TypeError("context_version must be an integer")
        if self.context_version < 1:
            raise ValueError("context_version must be positive")
        if not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be Provenance")
        if not isinstance(self.has_mock_evidence, bool):
            raise TypeError("has_mock_evidence must be a boolean")
        modes = {item.provenance.execution_mode for item in self.analyzer_results}
        if modes and modes != {self.provenance.execution_mode}:
            raise ValueError("assessment cannot mix execution modes")
        expected_mock = self.provenance.execution_mode is ExecutionMode.MOCK or any(
            item.provenance.execution_mode is ExecutionMode.MOCK for item in self.analyzer_results
        )
        if self.has_mock_evidence != expected_mock:
            raise ValueError("has_mock_evidence does not match provenance")


def _require_tuple(value: object, item_type: type[object], field_name: str) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise TypeError(f"{field_name} contains an invalid value")
