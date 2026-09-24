"""Freeze policy v2 on validation, then evaluate one untouched grouped test holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha_defense.application.detection.policy_mapping import risk_policy_from_snapshot
from alpha_defense.application.ports import TextAnalysisRequest
from alpha_defense.domain.detection import (
    AnalysisApplicability,
    AnalysisPlan,
    AnalysisRequirement,
    AnalysisResult,
    AnalysisStatus,
    AnalyzerKind,
    RiskPolicy,
)
from alpha_defense.domain.shared import ExecutionMode, Severity
from alpha_defense.infrastructure.analysis.ml import LocalTextModelAnalyzer
from alpha_defense.infrastructure.analysis.mock import DeterministicTextAnalyzer
from alpha_defense.infrastructure.content import LocalCatalogLoader

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "datasets/text/messages.v1.jsonl"
SPLIT_PATH = ROOT / "datasets/text/splits.v1.json"
MODEL_ROOT = ROOT / "artifacts/text"
VALIDATION_REPORT = MODEL_ROOT / "policy_validation.v2.json"
FREEZE_FILE = MODEL_ROOT / "policy_freeze.v2.json"
TEST_REPORT = MODEL_ROOT / "policy_test.v2.json"
EVALUATOR_VERSION = "text-policy-evaluation-v2"
POSITIVE_LABEL = "suspicious"
INPUTS = {
    "model": MODEL_ROOT / "model.v1.joblib",
    "model_manifest": MODEL_ROOT / "model.v1.json",
    "policy_v1": ROOT / "content/policies/demo-risk-v1.json",
    "policy_v2": ROOT / "content/policies/demo-risk-v2.json",
    "guidance_v2": ROOT / "content/recommendations/demo-guidance-ru-v2.json",
    "dataset": DATASET_PATH,
    "split_manifest": SPLIT_PATH,
    "evaluator": Path(__file__),
    "rule_adapter": ROOT
    / "apps/backend/src/alpha_defense/infrastructure/analysis/mock/text_rules.py",
    "model_adapter": ROOT
    / "apps/backend/src/alpha_defense/infrastructure/analysis/ml/text_model.py",
    "risk_policy": ROOT
    / "apps/backend/src/alpha_defense/domain/detection/risk_policy.py",
    "signal_contract": ROOT
    / "apps/backend/src/alpha_defense/domain/detection/signal.py",
    "policy_mapping": ROOT
    / "apps/backend/src/alpha_defense/application/detection/policy_mapping.py",
    "assessment_workflow": ROOT
    / "apps/backend/src/alpha_defense/application/detection/assess_observation.py",
    "analysis_plan": ROOT
    / "apps/backend/src/alpha_defense/application/detection/plan.py",
    "catalog_loader": ROOT
    / "apps/backend/src/alpha_defense/infrastructure/content/loader.py",
    "bootstrap": ROOT / "apps/backend/src/alpha_defense/bootstrap/container.py",
    "policy_schema": ROOT / "contracts/fixtures/policy.v1.schema.json",
}


@dataclass(frozen=True, slots=True)
class EvaluationRow:
    id: str
    text: str
    label: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _load_split(split: str) -> tuple[list[EvaluationRow], dict[str, str]]:
    if split not in {"validation", "test"}:
        raise ValueError("only validation and test are evaluation splits")
    dataset_bytes = DATASET_PATH.read_bytes()
    split_bytes = SPLIT_PATH.read_bytes()
    manifest: Any = json.loads(split_bytes)
    if _sha256(dataset_bytes) != manifest["dataset_sha256"]:
        raise ValueError("dataset hash differs from manifest")
    part = manifest["splits"][split]
    wanted_ids = set(part["ids"])
    rows: list[EvaluationRow] = []
    selected_lines: list[bytes] = []
    for line in dataset_bytes.splitlines(keepends=True):
        match = re.search(rb'"id":"(text-\d{4})"', line)
        if match is None:
            raise ValueError("dataset row lacks canonical ID")
        row_id = match.group(1).decode("ascii")
        if row_id not in wanted_ids:
            continue
        record: Any = json.loads(line)
        if record["template_group"] not in part["template_groups"]:
            raise ValueError("evaluation group differs from split manifest")
        rows.append(EvaluationRow(row_id, record["text"], record["label"]))
        selected_lines.append(line)
    if (
        {row.id for row in rows} != wanted_ids
        or len(rows) != part["count"]
        or _sha256(b"".join(selected_lines)) != part["content_sha256"]
        or Counter(row.label for row in rows) != part["label_counts"]
    ):
        raise ValueError("evaluation split differs from manifest")
    return rows, {
        "dataset_sha256": manifest["dataset_sha256"],
        "split_manifest_sha256": _sha256(split_bytes),
        "split_content_sha256": part["content_sha256"],
    }


def _catalog(version: str) -> LocalCatalogLoader:
    return LocalCatalogLoader(
        schema_root=ROOT / "contracts/fixtures",
        content_root=ROOT / "content",
        fixture_root=ROOT / "fixtures",
        policy_version=version,
    )


def _plan(*analyzers: AnalyzerKind) -> AnalysisPlan:
    return AnalysisPlan(
        version="offline-text-comparison-v2",
        requirements=tuple(
            AnalysisRequirement(
                kind, AnalysisApplicability.APPLICABLE, True, "analysis_required"
            )
            for kind in analyzers
        ),
    )


def _policy_prediction(
    policy: RiskPolicy, plan: AnalysisPlan, results: tuple[AnalysisResult, ...]
) -> bool | None:
    outcome = policy.evaluate(plan=plan, analyzer_results=results)
    if outcome.severity is Severity.UNKNOWN:
        return None
    return outcome.severity in {Severity.HIGH, Severity.CRITICAL}


def _metrics(
    rows: list[EvaluationRow], predictions: list[bool | None]
) -> dict[str, object]:
    actual_predictions = [
        (row, prediction)
        for row, prediction in zip(rows, predictions, strict=True)
        if prediction is not None
    ]
    tp = sum(
        row.label == POSITIVE_LABEL and prediction
        for row, prediction in actual_predictions
    )
    fp = sum(
        row.label != POSITIVE_LABEL and prediction
        for row, prediction in actual_predictions
    )
    fn = sum(
        row.label == POSITIVE_LABEL and not prediction
        for row, prediction in actual_predictions
    )
    tn = len(actual_predictions) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "n": len(rows),
        "evaluated": len(actual_predictions),
        "abstained_ids": [
            row.id
            for row, prediction in zip(rows, predictions, strict=True)
            if prediction is None
        ],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "error_ids": [
            row.id
            for row, prediction in actual_predictions
            if prediction != (row.label == POSITIVE_LABEL)
        ],
    }


def evaluate(split: str) -> bytes:
    rows, hashes = _load_split(split)
    v1_policy = risk_policy_from_snapshot(_catalog("demo-risk-v1").load_policy())
    v2_catalog = _catalog("demo-risk-v2").load()
    v2_policy = risk_policy_from_snapshot(v2_catalog.policy)
    rule_analyzer = DeterministicTextAnalyzer()
    model_analyzer = LocalTextModelAnalyzer.from_trusted_directory(MODEL_ROOT)
    rule_plan = _plan(AnalyzerKind.TEXT)
    combined_plan = _plan(AnalyzerKind.TEXT, AnalyzerKind.TEXT_MODEL)
    predicted: dict[str, list[bool | None]] = {"rules": [], "model": [], "combined": []}
    failures: Counter[str] = Counter()
    for row in rows:
        request = TextAnalysisRequest(
            text=row.text,
            evidence_ref=f"offline:{row.id}",
            execution_mode=ExecutionMode.MOCK,
        )
        rule_result = rule_analyzer.analyze(request)
        model_result = model_analyzer.analyze(request)
        if model_result.status is not AnalysisStatus.OK:
            failures[model_result.reason_codes[0]] += 1
        predicted["rules"].append(
            _policy_prediction(v1_policy, rule_plan, (rule_result,))
        )
        predicted["model"].append(
            bool(model_result.signals)
            if model_result.status is AnalysisStatus.OK
            else None
        )
        predicted["combined"].append(
            _policy_prediction(v2_policy, combined_plan, (rule_result, model_result))
        )
    return _json_bytes(
        {
            "evaluation_version": EVALUATOR_VERSION,
            "split": split,
            "positive_label": POSITIVE_LABEL,
            "n": len(rows),
            "label_counts": dict(sorted(Counter(row.label for row in rows).items())),
            "positive_cutoff": "high_or_critical",
            "model_version": "text-tfidf-logreg-v1",
            "rule_policy_version": v1_policy.policy_version,
            "combined_policy_version": v2_policy.policy_version,
            "model_failures": dict(sorted(failures.items())),
            "comparisons": {
                name: _metrics(rows, predictions)
                for name, predictions in predicted.items()
            },
            **hashes,
        }
    )


def _freeze_bytes(validation_bytes: bytes) -> bytes:
    model_manifest: Any = json.loads((MODEL_ROOT / "model.v1.json").read_bytes())
    return _json_bytes(
        {
            "evaluation_version": EVALUATOR_VERSION,
            "policy_version": "demo-risk-v2",
            "model_version": "text-tfidf-logreg-v1",
            "model_threshold": model_manifest["threshold"],
            "positive_cutoff": "high_or_critical",
            "validation_report_sha256": _sha256(validation_bytes),
            "input_sha256": {
                name: _sha256(path.read_bytes())
                for name, path in sorted(INPUTS.items())
            },
        }
    )


def _verify_freeze() -> None:
    if not VALIDATION_REPORT.is_file() or not FREEZE_FILE.is_file():
        raise SystemExit("validation policy has not been frozen")
    expected = _freeze_bytes(VALIDATION_REPORT.read_bytes())
    if FREEZE_FILE.read_bytes() != expected:
        raise SystemExit("policy or evaluation inputs changed after validation freeze")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("validation", "test"))
    parser.add_argument(
        "--write", action="store_true", help="write a new one-time report"
    )
    args = parser.parse_args()
    outputs: tuple[tuple[Path, bytes], ...]
    if args.split == "test":
        _verify_freeze()  # Must happen before any held-out row is parsed.
        if args.write and TEST_REPORT.exists():
            raise SystemExit("test report is already fixed; a new test set is required")
        report = evaluate("test")
        target = TEST_REPORT
        outputs = ((target, report),)
    else:
        if args.write and TEST_REPORT.exists():
            raise SystemExit(
                "test has been opened; validation policy cannot be retuned"
            )
        report = evaluate("validation")
        outputs = (
            (VALIDATION_REPORT, report),
            (FREEZE_FILE, _freeze_bytes(report)),
        )
    for path, expected in outputs:
        if args.write:
            path.write_bytes(expected)
        elif not path.is_file() or path.read_bytes() != expected:
            raise SystemExit(
                f"{path}: missing or stale; run with --write only before test"
            )
    values: Any = json.loads(report)
    print(
        f"validated {args.split} n={values['n']}; "
        f"rules={values['comparisons']['rules']['f1']:.4f}, "
        f"model={values['comparisons']['model']['f1']:.4f}, "
        f"combined={values['comparisons']['combined']['f1']:.4f}"
    )


if __name__ == "__main__":
    main()
