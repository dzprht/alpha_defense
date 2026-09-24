"""Acceptance checks for synthetic labels, uniqueness and grouped holdout."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace

import pytest

from scripts.ml import build_text_dataset as dataset


def test_committed_dataset_and_manifest_are_reproducible() -> None:
    expected_rows, expected_manifest = dataset.render_artifacts()
    assert dataset.DATASET_PATH.read_bytes() == expected_rows
    assert dataset.SPLIT_PATH.read_bytes() == expected_manifest

    rows = [json.loads(line) for line in expected_rows.splitlines()]
    manifest = json.loads(expected_manifest)
    assert len(rows) == 400
    assert Counter(row["label"] for row in rows) == {"benign": 200, "suspicious": 200}
    assert len({row["id"] for row in rows}) == 400
    assert len({dataset.normalized_words(row["text"]) for row in rows}) == 400
    assert manifest["dataset_sha256"] == dataset.sha256(expected_rows)
    assert manifest["source_sha256"] == dataset.sha256(dataset.SOURCE_PATH.read_bytes())
    assert manifest["split_seed"] == dataset.SPLIT_SEED
    assert not {dataset.normalized_words(text) for text in dataset.scenario_texts()} & {
        dataset.normalized_words(row["text"]) for row in rows
    }
    benign_texts = [row["text"].casefold() for row in rows if row["label"] == "benign"]
    assert all(
        any(cue in text for text in benign_texts) for cue in ("код", "сроч", "перевод")
    )


def test_splits_are_disjoint_and_keep_both_classes_and_sources() -> None:
    rows = [json.loads(line) for line in dataset.DATASET_PATH.read_bytes().splitlines()]
    manifest = json.loads(dataset.SPLIT_PATH.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in rows}
    split_ids = [set(part["ids"]) for part in manifest["splits"].values()]
    split_groups = [
        set(part["template_groups"]) for part in manifest["splits"].values()
    ]
    assert set.union(*split_ids) == set(by_id)
    assert len(set.union(*split_ids)) == sum(map(len, split_ids))
    assert len(set.union(*split_groups)) == sum(map(len, split_groups)) == 80

    for name, expected in (("train", 240), ("validation", 80), ("test", 80)):
        part = manifest["splits"][name]
        selected = [by_id[row_id] for row_id in part["ids"]]
        assert len(selected) == part["count"] == expected
        assert all(row["template_group"] in part["template_groups"] for row in selected)
        assert Counter(row["label"] for row in selected) == {
            "benign": expected // 2,
            "suspicious": expected // 2,
        }
        assert part["label_counts"] == dict(Counter(row["label"] for row in selected))
        assert {row["source_kind"] for row in selected} == dataset.SOURCE_KINDS
        assert part["source_kind_counts"] == dict(
            Counter(
                {row["template_group"]: row["source_kind"] for row in selected}.values()
            )
        )
        assert part["content_sha256"] == dataset.sha256(dataset.json_lines(selected))


def test_same_seed_repeats_group_split_and_different_seed_changes_it() -> None:
    groups = dataset.load_groups()
    first = dataset.split_groups(groups)
    assert dataset.split_groups(groups) == first
    assert dataset.split_groups(groups, dataset.SPLIT_SEED + 1) != first


def test_normalized_duplicate_in_another_group_is_rejected() -> None:
    groups = dataset.load_groups()
    replacement = replace(
        groups[1], texts=(groups[0].texts[0].upper(), *groups[1].texts[1:])
    )
    groups[1] = replacement
    with pytest.raises(ValueError, match="duplicate text"):
        dataset.validate_groups(groups, dataset.scenario_texts())


def test_near_duplicate_in_another_group_is_rejected() -> None:
    groups = dataset.load_groups()
    similar = groups[0].texts[0] + " Пожалуйста."
    groups[1] = replace(groups[1], texts=(similar, *groups[1].texts[1:]))
    with pytest.raises(ValueError, match="near-duplicate"):
        dataset.validate_groups(groups, dataset.scenario_texts())


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Откройте https://example.test и сообщите свой код для проверки кабинета.",
        "Позвоните по номеру +7 999 123 45 67 и назовите пароль оператору.",
    ],
)
def test_private_identifiers_and_urls_are_rejected(unsafe_text: str) -> None:
    groups = dataset.load_groups()
    groups[0] = replace(groups[0], texts=(unsafe_text, *groups[0].texts[1:]))
    with pytest.raises(ValueError, match="private data"):
        dataset.validate_groups(groups, dataset.scenario_texts())


def test_scenario_fixture_copy_is_rejected() -> None:
    groups = dataset.load_groups()
    with pytest.raises(ValueError, match="scenario fixture overlap"):
        dataset.validate_groups(groups, (groups[0].texts[0],))
