# ruff: noqa: RUF001
"""Load a verified local model once and expose inference through a plain analysis port."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import sys
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import joblib
import numpy
import scipy
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from alpha_defense.application.ports import TextAnalysisRequest
from alpha_defense.domain.detection import AnalysisResult, AnalysisStatus, AnalyzerKind, Signal
from alpha_defense.domain.shared import ExecutionMode, Provenance

MODEL_VERSION = "text-tfidf-logreg-v1"
MODEL_FILE = "model.v1.joblib"
MANIFEST_FILE = "model.v1.json"
MAX_ARTIFACT_BYTES = 10_000_000
MAX_TEXT_LENGTH = 30_000
POSITIVE_LABEL = "suspicious"


def _versions() -> dict[str, str]:
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "scikit_learn": sklearn.__version__,
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "joblib": joblib.__version__,
    }


class LocalTextModelAnalyzer:
    """Inference only: no fit, user-supplied path, or runtime corpus mutation."""

    def __init__(
        self, *, model: Pipeline, threshold: float, model_version: str, artifact_sha256: str
    ) -> None:
        self._model = model
        self._threshold = threshold
        self._model_version = model_version
        self._artifact_sha256 = artifact_sha256

    @classmethod
    def from_trusted_directory(cls, directory: Path) -> LocalTextModelAnalyzer:
        """The directory comes from operator configuration, never an HTTP body."""
        manifest: Any = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
        if (
            manifest.get("model_version") != MODEL_VERSION
            or manifest.get("model_file") != MODEL_FILE
            or manifest.get("positive_label") != POSITIVE_LABEL
            or manifest.get("versions") != _versions()
        ):
            raise ValueError("model manifest version or library versions differ")
        path = directory / MODEL_FILE
        if path.is_symlink() or not path.is_file():
            raise ValueError("model must be a regular local file")
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if (
            not payload
            or len(payload) > MAX_ARTIFACT_BYTES
            or len(payload) != manifest.get("artifact_bytes")
            or digest != manifest.get("artifact_sha256")
        ):
            raise ValueError("model artifact hash or size mismatch")
        threshold = manifest.get("threshold")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not 0 < threshold < 1
        ):
            raise ValueError("model threshold is invalid")
        model = joblib.load(io.BytesIO(payload))
        if (
            not isinstance(model, Pipeline)
            or not isinstance(model.named_steps.get("tfidf"), TfidfVectorizer)
            or not isinstance(model.named_steps.get("classifier"), LogisticRegression)
            or list(model.named_steps["classifier"].classes_) != ["benign", POSITIVE_LABEL]
        ):
            raise ValueError("model structure is invalid")
        return cls(
            model=model,
            threshold=float(threshold),
            model_version=MODEL_VERSION,
            artifact_sha256=digest,
        )

    def analyze(self, request: TextAnalysisRequest) -> AnalysisResult:
        if request.execution_mode is not ExecutionMode.MOCK:
            raise ValueError("synthetic text model is not a live provider")
        started_at = perf_counter_ns()
        text = request.text
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            return self._failure(
                request, AnalysisStatus.INSUFFICIENT_DATA, "ml_invalid_text", started_at
            )
        if re.search(r"[А-Яа-яЁё]", text) is None:
            return self._failure(
                request, AnalysisStatus.INSUFFICIENT_DATA, "ml_unsupported_language", started_at
            )
        try:
            matrix = self._model.named_steps["tfidf"].transform([text])
            if matrix.nnz == 0:
                return self._failure(
                    request, AnalysisStatus.INSUFFICIENT_DATA, "ml_empty_vector", started_at
                )
            classifier = self._model.named_steps["classifier"]
            score = float(classifier.predict_proba(matrix)[0, 1])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("invalid model probability")
        except Exception:
            return self._failure(
                request, AnalysisStatus.UNAVAILABLE, "ml_model_failure", started_at
            )
        signals = (
            (
                Signal(
                    code="ml_suspicious_text",
                    evidence_ref=request.evidence_ref,
                    strength=round(score * 100),
                    source="trained-text-model",
                ),
            )
            if score >= self._threshold
            else ()
        )
        return AnalysisResult(
            analyzer=AnalyzerKind.TEXT_MODEL,
            status=AnalysisStatus.OK,
            signals=signals,
            reason_codes=("ml_text_scored",),
            latency_ms=(perf_counter_ns() - started_at) // 1_000_000,
            provenance=self._provenance(request.execution_mode),
            model_score=score,
        )

    def _failure(
        self,
        request: TextAnalysisRequest,
        status: AnalysisStatus,
        reason_code: str,
        started_at: int,
    ) -> AnalysisResult:
        return AnalysisResult(
            analyzer=AnalyzerKind.TEXT_MODEL,
            status=status,
            signals=(),
            reason_codes=(reason_code,),
            latency_ms=(perf_counter_ns() - started_at) // 1_000_000,
            provenance=self._provenance(request.execution_mode),
        )

    def _provenance(self, execution_mode: ExecutionMode) -> Provenance:
        return Provenance(
            execution_mode=execution_mode,
            provider="trained-text-model",
            provider_version=self._model_version,
            data_version=self._artifact_sha256,
        )
