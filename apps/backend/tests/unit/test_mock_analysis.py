"""Focused tests for deterministic text and URL mock analyzers."""

from alpha_defense.application.ports import ResourceAnalysisRequest, TextAnalysisRequest
from alpha_defense.domain.shared import ExecutionMode
from alpha_defense.infrastructure.analysis.mock import (
    DeterministicTextAnalyzer,
    DeterministicUrlAnalyzer,
)


def test_text_markers_change_only_when_content_changes() -> None:
    analyzer = DeterministicTextAnalyzer()
    dangerous = analyzer.analyze(
        TextAnalysisRequest(
            text="Срочно подтвердите данные карты и никому не говорите.",
            evidence_ref="observation:1:text",
            execution_mode=ExecutionMode.MOCK,
        )
    )
    neutral = analyzer.analyze(
        TextAnalysisRequest(
            text="Встречаемся завтра в десять.",
            evidence_ref="observation:1:text",
            execution_mode=ExecutionMode.MOCK,
        )
    )

    assert {item.code for item in dangerous.signals} == {
        "credential_request",
        "urgency_or_secrecy",
    }
    assert neutral.signals == ()
    assert dangerous == analyzer.analyze(
        TextAnalysisRequest(
            text="Срочно подтвердите данные карты и никому не говорите.",
            evidence_ref="observation:1:text",
            execution_mode=ExecutionMode.MOCK,
        )
    )


def test_url_rules_separate_trusted_lookalike_and_unrelated_domains() -> None:
    analyzer = DeterministicUrlAnalyzer()

    def analyze(url: str) -> tuple[str, ...]:
        result = analyzer.analyze(
            ResourceAnalysisRequest(
                normalized_url=url,
                evidence_ref="observation:1:resource_url",
                trusted_domains=("alfabank.ru",),
                trusted_brand_names=("Альфа-Банк",),
                trusted_catalog_version="catalog-v1",
                execution_mode=ExecutionMode.MOCK,
            )
        )
        return tuple(item.code for item in result.signals)

    assert analyze("https://alfabank.ru/") == ()
    assert analyze("https://online.alfabank.ru/") == ()
    assert analyze("https://alfa-secure-check.test/card") == ("lookalike_domain",)
    assert analyze("https://example.test/") == ()
