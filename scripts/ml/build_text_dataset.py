"""Build and audit the versioned, manually labelled synthetic text dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATASET_VERSION = "synthetic-text-v1"
SPLIT_SEED = 20260924
LABELS = {"suspicious", "benign"}
SOURCE_KINDS = {"sms", "chat", "call_transcript"}
TEXTS_PER_GROUP = 5
MIN_TEXTS = 400
ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "datasets/text/source_groups.v1.jsonl"
DATASET_PATH = ROOT / "datasets/text/messages.v1.jsonl"
SPLIT_PATH = ROOT / "datasets/text/splits.v1.json"
SCENARIO_ROOT = ROOT / "fixtures"
PRIVATE_PATTERN = re.compile(
    r"(?:https?://|www\.|\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b|(?<!\d)\+?\d[\d ()-]{8,}\d(?!\d))",
    re.IGNORECASE,
)
SCENARIO_ID_PATTERN = re.compile(r"\bS(?:0[1-9]|1[0-5])\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SourceGroup:
    group_id: str
    label: str
    source_kind: str
    annotation_note: str
    texts: tuple[str, ...]


def normalized_words(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(re.findall(r"\w+", normalized, flags=re.UNICODE))


def shingles(words: tuple[str, ...]) -> frozenset[tuple[str, ...]]:
    return frozenset(zip(words, words[1:], words[2:], strict=False))


def load_groups(path: Path = SOURCE_PATH) -> list[SourceGroup]:
    groups: list[SourceGroup] = []
    seen_ids: set[str] = set()
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        candidate: Any = json.loads(line)
        if not isinstance(candidate, dict) or set(candidate) != {
            "group_id",
            "label",
            "source_kind",
            "annotation_note",
            "texts",
        }:
            raise ValueError(f"source group line {number}: invalid fields")
        group_id = candidate["group_id"]
        label = candidate["label"]
        source_kind = candidate["source_kind"]
        note = candidate["annotation_note"]
        texts = candidate["texts"]
        if not isinstance(group_id, str) or not re.fullmatch(
            r"(?:sus|ben)-\d{2}", group_id
        ):
            raise ValueError(f"source group line {number}: invalid group id")
        if group_id in seen_ids:
            raise ValueError(f"source group line {number}: duplicate group id")
        if (
            not isinstance(label, str)
            or label not in LABELS
            or group_id.startswith("sus-") != (label == "suspicious")
        ):
            raise ValueError(
                f"source group line {number}: invalid manually assigned label"
            )
        if not isinstance(source_kind, str) or source_kind not in SOURCE_KINDS:
            raise ValueError(f"source group line {number}: invalid source kind")
        if not isinstance(note, str) or len(note.strip()) < 20:
            raise ValueError(
                f"source group line {number}: missing annotation rationale"
            )
        if not isinstance(texts, list) or len(texts) != TEXTS_PER_GROUP:
            raise ValueError(f"source group line {number}: expected five formulations")
        if not all(isinstance(text, str) and 30 <= len(text) <= 500 for text in texts):
            raise ValueError(f"source group line {number}: invalid text length")
        seen_ids.add(group_id)
        groups.append(SourceGroup(group_id, label, source_kind, note, tuple(texts)))
    return groups


def scenario_texts(path: Path = SCENARIO_ROOT) -> tuple[str, ...]:
    found: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "text" and isinstance(item, str):
                    found.append(item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for fixture in sorted(path.rglob("*.json")):
        visit(json.loads(fixture.read_text(encoding="utf-8")))
    return tuple(found)


def validate_groups(groups: list[SourceGroup], excluded_texts: Iterable[str]) -> None:
    if sum(len(group.texts) for group in groups) < MIN_TEXTS:
        raise ValueError("dataset needs at least 400 texts")
    if Counter(group.label for group in groups) != {"suspicious": 40, "benign": 40}:
        raise ValueError("v1 requires forty independent groups per class")
    expected_sources = {"sms": 15, "chat": 15, "call_transcript": 10}
    for label in sorted(LABELS):
        actual_sources = Counter(
            group.source_kind for group in groups if group.label == label
        )
        if actual_sources != expected_sources:
            raise ValueError(f"{label}: source-kind groups are not balanced")

    seen: dict[tuple[str, ...], str] = {}
    distinct: list[tuple[str, frozenset[tuple[str, ...]]]] = []
    excluded_shingles = [
        (normalized_words(text), shingles(normalized_words(text)))
        for text in excluded_texts
    ]
    for group in groups:
        for text in group.texts:
            if (
                text != text.strip()
                or "\n" in text
                or PRIVATE_PATTERN.search(text)
                or SCENARIO_ID_PATTERN.search(text)
            ):
                raise ValueError(
                    f"{group.group_id}: private data, URL or malformed text"
                )
            words = normalized_words(text)
            if len(words) < 6:
                raise ValueError(
                    f"{group.group_id}: scenario copy or overly short text"
                )
            if words in seen:
                raise ValueError(f"{group.group_id}: duplicate text with {seen[words]}")
            seen[words] = group.group_id
            text_shingles = shingles(words)
            for excluded_words, excluded_ngrams in excluded_shingles:
                union = text_shingles | excluded_ngrams
                if words == excluded_words or (
                    union and len(text_shingles & excluded_ngrams) / len(union) >= 0.8
                ):
                    raise ValueError(f"{group.group_id}: scenario fixture overlap")
            for other_group, other_shingles in distinct:
                if other_group == group.group_id:
                    continue
                union = text_shingles | other_shingles
                if union and len(text_shingles & other_shingles) / len(union) >= 0.8:
                    raise ValueError(
                        f"near-duplicate texts in {group.group_id} and {other_group}"
                    )
            distinct.append((group.group_id, text_shingles))


def split_groups(
    groups: list[SourceGroup], seed: int = SPLIT_SEED
) -> dict[str, list[str]]:
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for group in groups:
        buckets[group.label, group.source_kind].append(group.group_id)
    result: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    rng = random.Random(seed)
    for bucket in sorted(buckets):
        ids = sorted(buckets[bucket])
        rng.shuffle(ids)
        train_end = round(len(ids) * 0.6)
        validation_end = train_end + round(len(ids) * 0.2)
        result["train"].extend(ids[:train_end])
        result["validation"].extend(ids[train_end:validation_end])
        result["test"].extend(ids[validation_end:])
    return {part: sorted(ids) for part, ids in result.items()}


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def json_lines(rows: list[dict[str, object]]) -> bytes:
    return b"".join(canonical_json(row) + b"\n" for row in rows)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render_artifacts(
    source_path: Path = SOURCE_PATH, scenario_root: Path = SCENARIO_ROOT
) -> tuple[bytes, bytes]:
    groups = load_groups(source_path)
    validate_groups(groups, scenario_texts(scenario_root))
    assignments = split_groups(groups)

    rows: list[dict[str, object]] = []
    for group in sorted(groups, key=lambda item: item.group_id):
        for text in group.texts:
            rows.append(
                {
                    "id": f"text-{len(rows) + 1:04d}",
                    "text": text,
                    "label": group.label,
                    "template_group": group.group_id,
                    "source_kind": group.source_kind,
                    "annotation_note": group.annotation_note,
                    "dataset_version": DATASET_VERSION,
                }
            )
    dataset_bytes = json_lines(rows)
    by_group = {group.group_id: group for group in groups}
    manifest_splits: dict[str, dict[str, object]] = {}
    for part, group_ids in assignments.items():
        selected = [row for row in rows if row["template_group"] in group_ids]
        manifest_splits[part] = {
            "ids": [row["id"] for row in selected],
            "template_groups": group_ids,
            "count": len(selected),
            "label_counts": dict(
                sorted(Counter(row["label"] for row in selected).items())
            ),
            "source_kind_counts": dict(
                sorted(
                    Counter(
                        by_group[group_id].source_kind for group_id in group_ids
                    ).items()
                )
            ),
            "content_sha256": sha256(json_lines(selected)),
        }
    manifest = {
        "dataset_version": DATASET_VERSION,
        "split_algorithm": "stratified-group-shuffle-v1",
        "split_seed": SPLIT_SEED,
        "source_sha256": sha256(source_path.read_bytes()),
        "dataset_sha256": sha256(dataset_bytes),
        "total_count": len(rows),
        "splits": manifest_splits,
    }
    return dataset_bytes, json.dumps(manifest, ensure_ascii=False, indent=2).encode(
        "utf-8"
    ) + b"\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="regenerate committed artifacts"
    )
    args = parser.parse_args()
    dataset_bytes, manifest_bytes = render_artifacts()
    for path, expected in ((DATASET_PATH, dataset_bytes), (SPLIT_PATH, manifest_bytes)):
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
        elif not path.is_file() or path.read_bytes() != expected:
            raise SystemExit(f"{path}: missing or stale; run with --write")
    print(
        f"validated {len(dataset_bytes.splitlines())} synthetic texts; sha256={sha256(dataset_bytes)}"
    )


if __name__ == "__main__":
    main()
