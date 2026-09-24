"""Analyzer signals, plans, and typed analyzer outcomes."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

from alpha_defense.domain.shared import Provenance

_STABLE_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class AnalyzerKind(StrEnum):
    TEXT = "text"
    TEXT_MODEL = "text_model"
    RESOURCE_URL = "resource_url"
    THREAT_LOOKUP = "threat_lookup"
    RESOURCE_VISUAL = "resource_visual"


class AnalysisApplicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"


class AnalysisStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class Signal:
    code: str
    evidence_ref: str
    strength: int
    source: str
    applicability: AnalysisApplicability = AnalysisApplicability.APPLICABLE

    def __post_init__(self) -> None:
        _require_code(self.code, "code")
        _require_text(self.evidence_ref, "evidence_ref", max_length=512)
        _require_text(self.source, "source", max_length=128)
        if isinstance(self.strength, bool) or not isinstance(self.strength, int):
            raise TypeError("strength must be an integer")
        if not 0 <= self.strength <= 100:
            raise ValueError("strength must be between 0 and 100")
        if self.applicability is not AnalysisApplicability.APPLICABLE:
            raise ValueError("stored signals must be applicable")


@dataclass(frozen=True, slots=True)
class AnalysisRequirement:
    analyzer: AnalyzerKind
    applicability: AnalysisApplicability
    required: bool
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.analyzer, AnalyzerKind):
            raise TypeError("analyzer must be an AnalyzerKind")
        if not isinstance(self.applicability, AnalysisApplicability):
            raise TypeError("applicability must be an AnalysisApplicability")
        if not isinstance(self.required, bool):
            raise TypeError("required must be a boolean")
        _require_code(self.reason_code, "reason_code")
        if self.applicability is AnalysisApplicability.NOT_APPLICABLE and self.required:
            raise ValueError("not-applicable analyzers cannot be required")


@dataclass(frozen=True, slots=True)
class AnalysisPlan:
    version: str
    requirements: tuple[AnalysisRequirement, ...]

    def __post_init__(self) -> None:
        _require_text(self.version, "version", max_length=64)
        if not isinstance(self.requirements, tuple) or any(
            not isinstance(item, AnalysisRequirement) for item in self.requirements
        ):
            raise TypeError("requirements must contain AnalysisRequirement values")
        analyzers = tuple(item.analyzer for item in self.requirements)
        if len(set(analyzers)) != len(analyzers):
            raise ValueError("analysis plan analyzers must be unique")

    def requirement_for(self, analyzer: AnalyzerKind) -> AnalysisRequirement:
        for requirement in self.requirements:
            if requirement.analyzer is analyzer:
                return requirement
        raise ValueError(f"analysis plan does not contain {analyzer.value}")


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analyzer: AnalyzerKind
    status: AnalysisStatus
    signals: tuple[Signal, ...]
    reason_codes: tuple[str, ...]
    latency_ms: int
    provenance: Provenance
    model_score: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.analyzer, AnalyzerKind):
            raise TypeError("analyzer must be an AnalyzerKind")
        if not isinstance(self.status, AnalysisStatus):
            raise TypeError("status must be an AnalysisStatus")
        if not isinstance(self.signals, tuple) or any(
            not isinstance(item, Signal) for item in self.signals
        ):
            raise TypeError("signals must contain Signal values")
        if self.status is not AnalysisStatus.OK and self.signals:
            raise ValueError("non-successful analyzer results cannot contain signals")
        if not isinstance(self.reason_codes, tuple):
            raise TypeError("reason_codes must be a tuple")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes must be unique")
        for reason_code in self.reason_codes:
            _require_code(reason_code, "reason_code")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int):
            raise TypeError("latency_ms must be an integer")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        if not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be Provenance")
        if self.model_score is not None:
            if (
                self.analyzer is not AnalyzerKind.TEXT_MODEL
                or self.status is not AnalysisStatus.OK
                or isinstance(self.model_score, bool)
                or not isinstance(self.model_score, (int, float))
                or not math.isfinite(self.model_score)
                or not 0 <= self.model_score <= 1
            ):
                raise ValueError("model_score requires a successful text model result in [0, 1]")
        elif self.analyzer is AnalyzerKind.TEXT_MODEL and self.status is AnalysisStatus.OK:
            raise ValueError("successful text model results require model_score")


def _require_code(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not _STABLE_CODE.fullmatch(value):
        raise ValueError(f"{field_name} must use lower snake case")


def _require_text(value: object, field_name: str, *, max_length: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip() or len(value) > max_length:
        raise ValueError(f"{field_name} must be non-empty, trimmed, and bounded")
