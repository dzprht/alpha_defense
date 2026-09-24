# ruff: noqa: RUF001
"""M03 contract for trusted model inference and unavailable outcomes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.catalog_helpers import REPOSITORY_ROOT

from alpha_defense.application.ports import TextAnalysisRequest
from alpha_defense.domain.detection import AnalysisStatus, AnalyzerKind
from alpha_defense.domain.shared import ExecutionMode
from alpha_defense.infrastructure.analysis.ml import LocalTextModelAnalyzer

MODEL_ROOT = REPOSITORY_ROOT / "artifacts/text"


def _request(text: str) -> TextAnalysisRequest:
    return TextAnalysisRequest(text, "observation:synthetic:text_model", ExecutionMode.MOCK)


def test_real_trained_model_returns_separate_score_and_version() -> None:
    analyzer = LocalTextModelAnalyzer.from_trusted_directory(MODEL_ROOT)
    result = analyzer.analyze(_request("Сообщите код подтверждения для перевода"))

    assert result.analyzer is AnalyzerKind.TEXT_MODEL
    assert result.status is AnalysisStatus.OK
    assert result.model_score is not None and 0 <= result.model_score <= 1
    assert result.provenance.provider_version == "text-tfidf-logreg-v1"
    assert (
        result.provenance.data_version
        == json.loads((MODEL_ROOT / "model.v1.json").read_text(encoding="utf-8"))["artifact_sha256"]
    )
    assert {signal.code for signal in result.signals} <= {"ml_suspicious_text"}
    assert all(signal.source == "trained-text-model" for signal in result.signals)


@pytest.mark.parametrize(
    ("text", "status", "reason"),
    [
        ("  ", AnalysisStatus.INSUFFICIENT_DATA, "ml_invalid_text"),
        ("а" * 30_001, AnalysisStatus.INSUFFICIENT_DATA, "ml_invalid_text"),
        (
            "Please confirm your transfer",
            AnalysisStatus.INSUFFICIENT_DATA,
            "ml_unsupported_language",
        ),
        ("ъэюяъэюяъэюя", AnalysisStatus.INSUFFICIENT_DATA, "ml_empty_vector"),
    ],
)
def test_unscorable_text_is_not_a_low_probability(
    text: str, status: AnalysisStatus, reason: str
) -> None:
    result = LocalTextModelAnalyzer.from_trusted_directory(MODEL_ROOT).analyze(_request(text))
    assert result.status is status
    assert result.model_score is None
    assert result.signals == ()
    assert result.reason_codes == (reason,)


def test_model_failure_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = LocalTextModelAnalyzer.from_trusted_directory(MODEL_ROOT)

    def fail(_: object) -> None:
        raise RuntimeError("synthetic estimator failure")

    monkeypatch.setattr(analyzer._model.named_steps["classifier"], "predict_proba", fail)
    result = analyzer.analyze(_request("Сообщите код подтверждения"))
    assert result.status is AnalysisStatus.UNAVAILABLE
    assert result.model_score is None
    assert result.reason_codes == ("ml_model_failure",)


def test_tampered_model_is_rejected_before_deserialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "model.v1.json").write_bytes((MODEL_ROOT / "model.v1.json").read_bytes())
    (tmp_path / "model.v1.joblib").write_bytes((MODEL_ROOT / "model.v1.joblib").read_bytes() + b"x")
    monkeypatch.setattr(
        "alpha_defense.infrastructure.analysis.ml.text_model.joblib.load",
        lambda _: pytest.fail("deserialized before hash verification"),
    )
    with pytest.raises(ValueError, match="hash or size mismatch"):
        LocalTextModelAnalyzer.from_trusted_directory(tmp_path)


def test_live_mode_is_not_misrepresented_as_trained_live_service() -> None:
    analyzer = LocalTextModelAnalyzer.from_trusted_directory(MODEL_ROOT)
    with pytest.raises(ValueError, match="not a live provider"):
        analyzer.analyze(
            TextAnalysisRequest(
                "Сообщите код подтверждения", "observation:synthetic:text_model", ExecutionMode.LIVE
            )
        )
