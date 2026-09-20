"""Acceptance tests for strict versioned local catalog loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.catalog_helpers import install_valid_catalog

from alpha_defense.infrastructure.content import CatalogValidationError, LocalCatalogLoader


def _loader(tmp_path: Path) -> LocalCatalogLoader:
    return LocalCatalogLoader(
        schema_root=tmp_path / "schemas",
        content_root=tmp_path / "content",
        fixture_root=tmp_path / "fixtures",
        policy_version="demo-risk-v1",
    )


def _read_object(path: Path) -> dict[str, Any]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def catalog_root(tmp_path: Path) -> Path:
    install_valid_catalog(tmp_path)
    return tmp_path


def test_valid_s01_catalog_loads_plain_snapshots(catalog_root: Path) -> None:
    snapshot = _loader(catalog_root).load()

    assert snapshot.policy.policy_version == "demo-risk-v1"
    assert snapshot.policy.score_kind == "heuristic"
    assert len(snapshot.policy.signals) == 13
    assert snapshot.trusted_entities.source == "alpha-defense-synthetic"
    assert len(snapshot.trusted_entities.entities) == 3
    assert [(item.fixture_id, item.kind) for item in snapshot.fixtures] == [
        ("s01-card-block-sms", "communication"),
        ("s01-phishing-url", "threat"),
    ]
    assert snapshot.fixtures[0].refs[0].fixture_id == "s01-phishing-url"
    assert len(snapshot.catalog_sha256) == 64


def test_corrupted_json_is_rejected(catalog_root: Path) -> None:
    policy = catalog_root / "content" / "policies" / "demo-risk-v1.json"
    policy.write_text('{"schema_version": ', encoding="utf-8")

    with pytest.raises(CatalogValidationError) as captured:
        _loader(catalog_root).load()

    assert captured.value.code == "invalid_json"


def test_unknown_enum_is_rejected(catalog_root: Path) -> None:
    threat = catalog_root / "fixtures" / "threats" / "s01-phishing-url.v1.json"
    document = _read_object(threat)
    document["kind"] = "unknown"
    _write_object(threat, document)

    with pytest.raises(CatalogValidationError) as captured:
        _loader(catalog_root).load()

    assert captured.value.code == "schema_validation_failed"


def test_reference_outside_fixture_root_is_rejected(catalog_root: Path) -> None:
    communication = catalog_root / "fixtures" / "communications" / "s01-card-block-sms.v1.json"
    document = _read_object(communication)
    refs = document["refs"]
    assert isinstance(refs, list) and isinstance(refs[0], dict)
    refs[0]["path"] = "threats/../../outside.json"
    _write_object(communication, document)

    with pytest.raises(CatalogValidationError) as captured:
        _loader(catalog_root).load()

    assert captured.value.code == "unsafe_reference"


def test_unknown_fixture_version_is_rejected(catalog_root: Path) -> None:
    threat = catalog_root / "fixtures" / "threats" / "s01-phishing-url.v1.json"
    document = _read_object(threat)
    document["fixture_version"] = "2.0.0"
    _write_object(threat, document)

    with pytest.raises(CatalogValidationError) as captured:
        _loader(catalog_root).load()

    assert captured.value.code == "unsupported_version"


def test_wrong_content_hash_is_rejected(catalog_root: Path) -> None:
    policy = catalog_root / "content" / "policies" / "demo-risk-v1.json"
    document = _read_object(policy)
    document["content_sha256"] = "0" * 64
    _write_object(policy, document)

    with pytest.raises(CatalogValidationError) as captured:
        _loader(catalog_root).load()

    assert captured.value.code == "hash_mismatch"


def test_wrong_reference_hash_is_rejected(catalog_root: Path) -> None:
    communication = catalog_root / "fixtures" / "communications" / "s01-card-block-sms.v1.json"
    document = _read_object(communication)
    refs = document["refs"]
    assert isinstance(refs, list) and isinstance(refs[0], dict)
    refs[0]["sha256"] = "0" * 64
    _write_object(communication, document)

    with pytest.raises(CatalogValidationError) as captured:
        _loader(catalog_root).load()

    assert captured.value.code == "hash_mismatch"


def test_invalid_observation_payload_is_rejected_by_its_feature_schema(
    catalog_root: Path,
) -> None:
    communication = catalog_root / "fixtures" / "communications" / "s01-card-block-sms.v1.json"
    document = _read_object(communication)
    payload = document["payload"]
    assert isinstance(payload, dict)
    message = payload["payload"]
    assert isinstance(message, dict)
    message["text"] = ""
    _write_object(communication, document)

    with pytest.raises(CatalogValidationError) as captured:
        _loader(catalog_root).load()

    assert captured.value.code == "schema_validation_failed"
