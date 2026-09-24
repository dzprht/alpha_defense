"""Train and verify the versioned text model without opening the test holdout."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy
import scipy
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "datasets/text/messages.v1.jsonl"
SPLIT_PATH = ROOT / "datasets/text/splits.v1.json"
ARTIFACT_DIR = ROOT / "artifacts/text"
MODEL_VERSION = "text-tfidf-logreg-v1"
MODEL_FILE = "model.v1.joblib"
MANIFEST_FILE = "model.v1.json"
REPORT_FILE = "validation.v1.json"
POSITIVE_LABEL = "suspicious"
SEED = 20260924
MAX_TEXT_LENGTH = 30_000
MAX_ARTIFACT_BYTES = 10_000_000
THRESHOLDS = tuple(round(number / 100, 2) for number in range(5, 96, 5))


@dataclass(frozen=True, slots=True)
class SplitRow:
    text: str
    label: str


@dataclass(frozen=True, slots=True)
class TextScore:
    status: Literal["complete", "unavailable"]
    probability: float | None
    is_suspicious: bool | None
    reason: str | None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _versions() -> dict[str, str]:
    return {
        "python": ".".join(str(part) for part in sys.version_info[:2]),
        "scikit_learn": sklearn.__version__,
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "joblib": joblib.__version__,
    }


def load_training_splits(
    dataset_path: Path = DATASET_PATH, split_path: Path = SPLIT_PATH
) -> tuple[dict[str, list[SplitRow]], dict[str, str]]:
    """Read only train/validation content; use test metadata solely for disjointness."""
    dataset_bytes = dataset_path.read_bytes()
    split_bytes = split_path.read_bytes()
    manifest: Any = json.loads(split_bytes)
    if manifest.get("dataset_sha256") != _sha256(dataset_bytes):
        raise ValueError("dataset hash differs from the split manifest")
    parts = manifest.get("splits")
    if not isinstance(parts, dict) or set(parts) != {"train", "validation", "test"}:
        raise ValueError("expected train/validation/test split metadata")
    id_sets = {name: set(parts[name]["ids"]) for name in parts}
    group_sets = {name: set(parts[name]["template_groups"]) for name in parts}
    if len(set.union(*id_sets.values())) != sum(map(len, id_sets.values())):
        raise ValueError("split IDs overlap")
    if len(set.union(*group_sets.values())) != sum(map(len, group_sets.values())):
        raise ValueError("template groups overlap")

    selected_lines: dict[str, list[bytes]] = {"train": [], "validation": []}
    selected_rows: dict[str, list[SplitRow]] = {"train": [], "validation": []}
    seen_ids: set[str] = set()
    for line in dataset_bytes.splitlines(keepends=True):
        # Dataset v1 uses canonical JSONL; inspect only the ID of held-out rows.
        id_match = re.search(rb'"id":"(text-\d{4})"', line)
        if id_match is None:
            raise ValueError("dataset row has no canonical ID")
        row_id = id_match.group(1).decode("ascii")
        if row_id in seen_ids:
            raise ValueError("duplicate dataset ID")
        seen_ids.add(row_id)
        for name in ("train", "validation"):
            if row_id not in id_sets[name]:
                continue
            row: Any = json.loads(line)
            if (
                row.get("template_group") not in group_sets[name]
                or row.get("label") not in {"benign", POSITIVE_LABEL}
                or not isinstance(row.get("text"), str)
                or not row["text"].strip()
            ):
                raise ValueError(f"{name}: invalid row or group")
            selected_lines[name].append(line)
            selected_rows[name].append(SplitRow(row["text"], row["label"]))
            break
    if seen_ids != set.union(*id_sets.values()):
        raise ValueError("dataset IDs differ from split manifest")
    for name, rows in selected_rows.items():
        expected = parts[name]
        if (
            len(rows) != expected["count"]
            or _sha256(b"".join(selected_lines[name])) != expected["content_sha256"]
            or Counter(row.label for row in rows) != expected["label_counts"]
        ):
            raise ValueError(f"{name}: content differs from split manifest")
    hashes = {
        "dataset_sha256": _sha256(dataset_bytes),
        "split_manifest_sha256": _sha256(split_bytes),
        "train_content_sha256": parts["train"]["content_sha256"],
        "validation_content_sha256": parts["validation"]["content_sha256"],
    }
    return selected_rows, hashes


def _metrics(labels: list[str], predictions: list[bool]) -> dict[str, object]:
    tp = sum(
        label == POSITIVE_LABEL and predicted
        for label, predicted in zip(labels, predictions, strict=True)
    )
    fp = sum(
        label != POSITIVE_LABEL and predicted
        for label, predicted in zip(labels, predictions, strict=True)
    )
    fn = sum(
        label == POSITIVE_LABEL and not predicted
        for label, predicted in zip(labels, predictions, strict=True)
    )
    tn = len(labels) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "n": len(labels),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def _choose_threshold(
    labels: list[str], scores: list[float]
) -> tuple[float, dict[str, object]]:
    choices = [
        (threshold, _metrics(labels, [score >= threshold for score in scores]))
        for threshold in THRESHOLDS
    ]
    # Predeclared: max F1, then recall, then nearest to 0.5, then lower threshold.
    return max(
        choices,
        key=lambda item: (
            item[1]["f1"],
            item[1]["recall"],
            -abs(item[0] - 0.5),
            -item[0],
        ),
    )


def train() -> tuple[bytes, bytes, bytes]:
    splits, hashes = load_training_splits()
    train_rows = splits["train"]
    validation_rows = splits["validation"]
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
            (
                "classifier",
                LogisticRegression(
                    solver="liblinear", random_state=SEED, max_iter=1000
                ),
            ),
        ]
    )
    model.fit([row.text for row in train_rows], [row.label for row in train_rows])
    scores = model.predict_proba([row.text for row in validation_rows])[
        :, list(model.classes_).index(POSITIVE_LABEL)
    ].tolist()
    threshold, metrics = _choose_threshold(
        [row.label for row in validation_rows], scores
    )
    # scikit-learn caches id(stop_words) during fit. This process address is
    # irrelevant to inference but makes identical joblib files differ.
    delattr(model.named_steps["tfidf"], "_stop_words_id")
    output = io.BytesIO()
    joblib.dump(model, output, compress=0, protocol=5)
    model_bytes = output.getvalue()
    versions = _versions()
    report = {
        "model_version": MODEL_VERSION,
        "evaluated_split": "validation",
        "n_train": len(train_rows),
        "n_validation": len(validation_rows),
        "threshold_selection": "max_f1_then_recall_then_nearest_0.5_then_lower",
        "candidate_thresholds": list(THRESHOLDS),
        "selected_threshold": threshold,
        "positive_label": POSITIVE_LABEL,
        "metrics": metrics,
        "test_evaluated": False,
        **hashes,
    }
    report_bytes = _json_bytes(report)
    artifact = {
        "model_version": MODEL_VERSION,
        "model_file": MODEL_FILE,
        "artifact_sha256": _sha256(model_bytes),
        "artifact_bytes": len(model_bytes),
        "validation_report_sha256": _sha256(report_bytes),
        "threshold": threshold,
        "positive_label": POSITIVE_LABEL,
        "seed": SEED,
        "versions": versions,
        "features": {"kind": "word_tfidf", "ngram_range": [1, 2], "sublinear_tf": True},
        "classifier": {"kind": "logistic_regression", "solver": "liblinear", "C": 1.0},
        **hashes,
    }
    return model_bytes, _json_bytes(artifact), report_bytes


def load_trusted_model() -> tuple[Pipeline, float]:
    """Load only the checked-in local artifact; never accept a user-supplied path."""
    manifest: Any = json.loads(
        (ARTIFACT_DIR / MANIFEST_FILE).read_text(encoding="utf-8")
    )
    if (
        manifest.get("model_version") != MODEL_VERSION
        or manifest.get("versions") != _versions()
    ):
        raise ValueError("model version or runtime dependency versions differ")
    if manifest.get("model_file") != MODEL_FILE:
        raise ValueError("unexpected model artifact name")
    path = ARTIFACT_DIR / MODEL_FILE
    if path.is_symlink() or not path.is_file():
        raise ValueError("model artifact must be a regular local file")
    model_bytes = path.read_bytes()
    if (
        len(model_bytes) > MAX_ARTIFACT_BYTES
        or len(model_bytes) != manifest.get("artifact_bytes")
        or _sha256(model_bytes) != manifest.get("artifact_sha256")
    ):
        raise ValueError("model artifact hash or size mismatch")
    model = joblib.load(io.BytesIO(model_bytes))
    if (
        not isinstance(model, Pipeline)
        or not isinstance(model.named_steps.get("tfidf"), TfidfVectorizer)
        or not isinstance(model.named_steps.get("classifier"), LogisticRegression)
    ):
        raise TypeError("unexpected model artifact structure")
    threshold = manifest.get("threshold")
    if not isinstance(threshold, (int, float)) or not 0 < threshold < 1:
        raise ValueError("invalid model threshold")
    return model, float(threshold)


def score_text(model: Pipeline, threshold: float, text: object) -> TextScore:
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        return TextScore("unavailable", None, None, "invalid_text")
    if re.search(r"[А-Яа-яЁё]", text) is None:
        return TextScore("unavailable", None, None, "unsupported_language")
    try:
        matrix = model.named_steps["tfidf"].transform([text])
        if matrix.nnz == 0:
            return TextScore("unavailable", None, None, "empty_vector")
        classifier = model.named_steps["classifier"]
        probability = float(
            classifier.predict_proba(matrix)[
                0, list(classifier.classes_).index(POSITIVE_LABEL)
            ]
        )
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            return TextScore("unavailable", None, None, "model_failure")
    except (AttributeError, IndexError, RuntimeError, TypeError, ValueError):
        return TextScore("unavailable", None, None, "model_failure")
    return TextScore("complete", probability, probability >= threshold, None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="write the versioned model artifacts"
    )
    args = parser.parse_args()
    expected = train()
    for name, data in zip(
        (MODEL_FILE, MANIFEST_FILE, REPORT_FILE), expected, strict=True
    ):
        path = ARTIFACT_DIR / name
        if args.write:
            ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        elif not path.is_file() or path.read_bytes() != data:
            raise SystemExit(f"{path}: missing or stale; rerun with --write")
    model, threshold = load_trusted_model()
    print(
        f"validated {MODEL_VERSION}; sha256={_sha256(expected[0])}; threshold={threshold}; vocabulary={len(model.named_steps['tfidf'].vocabulary_)}"
    )


if __name__ == "__main__":
    main()
