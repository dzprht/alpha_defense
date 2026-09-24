"""Acceptance checks for isolated, holdout-safe text-model training."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy
import pytest
from sklearn.pipeline import Pipeline

from scripts.ml import train_text_classifier as training


def test_committed_model_and_validation_are_byte_reproducible() -> None:
    first = training.train()
    second = training.train()
    assert first == second
    for name, expected in zip(
        (training.MODEL_FILE, training.MANIFEST_FILE, training.REPORT_FILE),
        first,
        strict=True,
    ):
        assert (training.ARTIFACT_DIR / name).read_bytes() == expected
    manifest = json.loads(first[1])
    report = json.loads(first[2])
    assert manifest["artifact_sha256"] == training._sha256(first[0])
    assert manifest["dataset_sha256"] == report["dataset_sha256"]
    assert report["evaluated_split"] == "validation"
    assert report["test_evaluated"] is False
    assert report["n_train"] == 240
    assert report["n_validation"] == 80
    assert sum(report["metrics"]["confusion_matrix"].values()) == 80


def test_fit_receives_train_texts_only(monkeypatch: pytest.MonkeyPatch) -> None:
    splits, _ = training.load_training_splits()
    expected = [row.text for row in splits["train"]]
    original = Pipeline.fit
    seen: list[list[str]] = []

    def spy(self: Pipeline, texts: list[str], labels: list[str]) -> Pipeline:
        seen.append(texts)
        assert labels == [row.label for row in splits["train"]]
        return original(self, texts, labels)

    monkeypatch.setattr(Pipeline, "fit", spy)
    training.train()
    assert seen == [expected]
    assert set(expected).isdisjoint(row.text for row in splits["validation"])


def test_test_rows_are_not_deserialized(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = json.loads(training.SPLIT_PATH.read_text(encoding="utf-8"))
    test_ids = set(manifest["splits"]["test"]["ids"])
    original = json.loads

    def guarded_loads(value: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(value, bytes):
            match = re.search(rb'"id":"(text-\d{4})"', value)
            if match and match.group(1).decode("ascii") in test_ids:
                raise AssertionError("held-out row was deserialized")
        return original(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", guarded_loads)
    splits, _ = training.load_training_splits()
    assert set(splits) == {"train", "validation"}


def test_tampered_dataset_hash_fails_before_fit(tmp_path: Path) -> None:
    dataset_path = tmp_path / "messages.jsonl"
    dataset_path.write_bytes(training.DATASET_PATH.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="dataset hash"):
        training.load_training_splits(dataset_path=dataset_path)


def test_threshold_selection_uses_predeclared_tie_break() -> None:
    threshold, metrics = training._choose_threshold(
        ["suspicious", "benign"], [0.9, 0.1]
    )
    assert threshold == 0.5
    assert metrics["f1"] == 1.0


def test_text_input_and_empty_vector_are_explicitly_unavailable() -> None:
    model, threshold = training.load_trusted_model()
    for text, reason in (
        (None, "invalid_text"),
        ("   ", "invalid_text"),
        ("а" * (training.MAX_TEXT_LENGTH + 1), "invalid_text"),
        ("Please transfer money immediately", "unsupported_language"),
        ("ъэюяъэюяъэюя", "empty_vector"),
    ):
        result = training.score_text(model, threshold, text)
        assert result.status == "unavailable"
        assert result.reason == reason
        assert result.probability is None
        assert result.is_suspicious is None
    scored = training.score_text(
        model, threshold, "Сообщите код подтверждения для перевода"
    )
    assert scored.status == "complete"
    assert scored.probability is not None and 0 <= scored.probability <= 1
    assert scored.is_suspicious == (scored.probability >= threshold)


def test_scoring_failure_is_not_reported_as_low_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, threshold = training.load_trusted_model()

    def fail(_: object) -> None:
        raise RuntimeError("synthetic model failure")

    monkeypatch.setattr(model.named_steps["classifier"], "predict_proba", fail)
    result = training.score_text(model, threshold, "Сообщите код подтверждения")
    assert result == training.TextScore("unavailable", None, None, "model_failure")

    monkeypatch.setattr(
        model.named_steps["classifier"],
        "predict_proba",
        lambda _: numpy.array([[float("nan"), float("nan")]]),
    )
    assert training.score_text(model, threshold, "Сообщите код подтверждения") == result


def test_tampered_or_symlinked_artifact_is_not_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / training.MANIFEST_FILE
    model_path = tmp_path / training.MODEL_FILE
    manifest_path.write_bytes(
        (training.ARTIFACT_DIR / training.MANIFEST_FILE).read_bytes()
    )
    model_path.write_bytes(
        (training.ARTIFACT_DIR / training.MODEL_FILE).read_bytes() + b"x"
    )
    monkeypatch.setattr(training, "ARTIFACT_DIR", tmp_path)
    with pytest.raises(ValueError, match="hash or size mismatch"):
        training.load_trusted_model()
    model_path.unlink()
    model_path.symlink_to(training.ROOT / "artifacts/text" / training.MODEL_FILE)
    with pytest.raises(ValueError, match="regular local file"):
        training.load_trusted_model()


def test_version_mismatch_is_rejected_before_deserialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = json.loads((training.ARTIFACT_DIR / training.MANIFEST_FILE).read_text())
    manifest["versions"]["scikit_learn"] = "different"
    (tmp_path / training.MANIFEST_FILE).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setattr(training, "ARTIFACT_DIR", tmp_path)
    with pytest.raises(ValueError, match="dependency versions"):
        training.load_trusted_model()
