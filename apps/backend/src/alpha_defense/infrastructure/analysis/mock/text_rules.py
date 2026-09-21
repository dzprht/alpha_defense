# ruff: noqa: RUF001
"""Deterministic Russian-language marker rules for the mock prototype."""

from __future__ import annotations

import re
from dataclasses import dataclass

from alpha_defense.application.ports import TextAnalysisRequest
from alpha_defense.domain.detection import AnalysisResult, AnalysisStatus, AnalyzerKind, Signal
from alpha_defense.domain.shared import Provenance

TEXT_RULES_VERSION = "ru-text-rules-v1"


@dataclass(frozen=True, slots=True)
class _MarkerRule:
    signal_code: str
    required_groups: tuple[tuple[re.Pattern[str], ...], ...]

    def matches(self, value: str) -> bool:
        return all(
            any(pattern.search(value) for pattern in group) for group in self.required_groups
        )


def _patterns(*values: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(value, re.IGNORECASE) for value in values)


_RULES = (
    _MarkerRule(
        "urgency_or_secrecy",
        (_patterns(r"\bсрочн\w*", r"\bнемедленн\w*", r"никому\s+не\s+говор", r"\bсекрет"),),
    ),
    _MarkerRule(
        "prize_fee_request",
        (
            _patterns(r"\bвыигр\w*", r"\bприз\w*", r"\bлотере\w*"),
            _patterns(r"\bкомисси\w*", r"\bпошлин\w*", r"\bоплат\w*", r"\bперевед\w*"),
        ),
    ),
    _MarkerRule(
        "delivery_fee_request",
        (
            _patterns(r"\bдостав\w*", r"\bпосыл\w*", r"\bкурьер\w*"),
            _patterns(r"\bоплат\w*", r"\bсбор\w*", r"\bперевед\w*"),
        ),
    ),
    _MarkerRule(
        "relative_emergency_payment",
        (
            _patterns(r"\bсын\w*", r"\bдоч\w*", r"\bвнук\w*", r"\bродственник\w*"),
            _patterns(r"\bбед\w*", r"\bавари\w*", r"\bбольниц\w*", r"\bполици\w*"),
            _patterns(r"\bденьг\w*", r"\bоплат\w*", r"\bперевед\w*"),
        ),
    ),
    _MarkerRule(
        "credential_request",
        (
            _patterns(
                r"код\w*\s+(?:из\s+)?смс",
                r"\bпарол\w*",
                r"\bcvv\b",
                r"данн\w*\s+карт\w*",
                r"подтверд\w*\s+данн\w*",
            ),
        ),
    ),
    _MarkerRule(
        "safe_account_transfer",
        (_patterns(r"безопасн\w*\s+(?:счет|счёт)", r"резервн\w*\s+(?:счет|счёт)"),),
    ),
)


class DeterministicTextAnalyzer:
    """Return stable signals only from explicit marker groups; no model is involved."""

    def analyze(self, request: TextAnalysisRequest) -> AnalysisResult:
        normalized = request.text.casefold().replace("ё", "е")
        signals = tuple(
            Signal(
                code=rule.signal_code,
                evidence_ref=request.evidence_ref,
                strength=100,
                source="deterministic-text-rules",
            )
            for rule in _RULES
            if rule.matches(normalized)
        )
        return AnalysisResult(
            analyzer=AnalyzerKind.TEXT,
            status=AnalysisStatus.OK,
            signals=signals,
            reason_codes=("deterministic_text_rules_applied",),
            latency_ms=0,
            provenance=Provenance(
                execution_mode=request.execution_mode,
                provider="deterministic-text-rules",
                provider_version=TEXT_RULES_VERSION,
                data_version=TEXT_RULES_VERSION,
            ),
        )
