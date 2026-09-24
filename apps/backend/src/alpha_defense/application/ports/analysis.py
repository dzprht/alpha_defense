"""Analyzer ports used by the observation risk assessment use case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from alpha_defense.domain.detection import AnalysisResult
from alpha_defense.domain.shared import ExecutionMode


@dataclass(frozen=True, slots=True)
class TextAnalysisRequest:
    text: str
    evidence_ref: str
    execution_mode: ExecutionMode


@dataclass(frozen=True, slots=True)
class ResourceAnalysisRequest:
    normalized_url: str
    evidence_ref: str
    trusted_domains: tuple[str, ...]
    trusted_brand_names: tuple[str, ...]
    trusted_catalog_version: str
    execution_mode: ExecutionMode


class TextAnalysisPort(Protocol):
    def analyze(self, request: TextAnalysisRequest) -> AnalysisResult: ...


class TextModelAnalysisPort(Protocol):
    def analyze(self, request: TextAnalysisRequest) -> AnalysisResult: ...


class ResourceAnalysisPort(Protocol):
    def analyze(self, request: ResourceAnalysisRequest) -> AnalysisResult: ...
