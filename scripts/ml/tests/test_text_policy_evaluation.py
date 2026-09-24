"""Validate the policy-freeze gate without opening held-out test content."""

from __future__ import annotations

import json
import re
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from scripts.ml import evaluate_text_policy as evaluation


def test_validation_report_and_frozen_policy_inputs_are_reproducible() -> None:
    report = evaluation.evaluate("validation")
    assert report == evaluation.VALIDATION_REPORT.read_bytes()
    freeze = json.loads(evaluation.FREEZE_FILE.read_bytes())
    assert freeze["validation_report_sha256"] == sha256(report).hexdigest()
    # The application bootstrap evolves after M03; the frozen evaluation remains
    # an archive of the M03 run, not a claim that later application code was tested.
    for name, path in evaluation.INPUTS.items():
        if name != "bootstrap":
            assert freeze["input_sha256"][name] == sha256(path.read_bytes()).hexdigest()
    parsed = json.loads(report)
    assert parsed["split"] == "validation"
    assert parsed["n"] == 80
    assert parsed["label_counts"] == {"benign": 40, "suspicious": 40}
    assert set(parsed["comparisons"]) == {"rules", "model", "combined"}
    assert all(item["n"] == 80 for item in parsed["comparisons"].values())
    assert all("text" not in item for item in parsed["comparisons"].values())


def test_validation_loader_does_not_deserialize_test_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = json.loads(evaluation.SPLIT_PATH.read_text(encoding="utf-8"))
    test_ids = set(manifest["splits"]["test"]["ids"])
    original = json.loads

    def guarded_loads(value: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(value, bytes):
            match = re.search(rb'"id":"(text-\d{4})"', value)
            if match and match.group(1).decode("ascii") in test_ids:
                raise AssertionError("held-out row was deserialized")
        return original(value, *args, **kwargs)

    monkeypatch.setattr(json, "loads", guarded_loads)
    rows, _ = evaluation._load_split("validation")
    assert len(rows) == 80


def test_stale_freeze_blocks_test_before_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / "stale.json"
    stale.write_bytes(b"{}")
    monkeypatch.setattr(evaluation, "FREEZE_FILE", stale)

    def must_not_evaluate(_: str) -> bytes:
        raise AssertionError("test evaluation started before freeze check")

    monkeypatch.setattr(evaluation, "evaluate", must_not_evaluate)
    monkeypatch.setattr(sys, "argv", ["evaluate_text_policy.py", "test"])
    with pytest.raises(SystemExit, match="changed after validation freeze"):
        evaluation.main()


def test_abstention_is_neither_false_negative_nor_low_risk() -> None:
    rows = [
        evaluation.EvaluationRow("first", "synthetic example one", "suspicious"),
        evaluation.EvaluationRow("second", "synthetic example two", "benign"),
    ]
    metrics = evaluation._metrics(rows, [None, False])
    assert metrics["n"] == 2
    assert metrics["evaluated"] == 1
    assert metrics["abstained_ids"] == ["first"]
    assert metrics["confusion_matrix"] == {"tn": 1, "fp": 0, "fn": 0, "tp": 0}
