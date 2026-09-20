"""Strict local loaders for versioned policies, trusted data, and fixtures."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from alpha_defense.application.ports import (
    CatalogSnapshot,
    FixtureEnvelope,
    FixtureReference,
    JsonValue,
    PolicySnapshot,
    RiskThresholds,
    SignalPolicy,
    TrustedEntitiesSnapshot,
    TrustedEntity,
)

SCHEMA_VERSION = "1.0"
FIXTURE_VERSION = "1.0.0"
TRUSTED_ENTITIES_FILE = "demo-trusted-entities-v1.json"
MAX_JSON_BYTES = 1_048_576

_POLICY_SCHEMA = "policy.v1.schema.json"
_TRUSTED_SCHEMA = "trusted-entities.v1.schema.json"
_FIXTURE_SCHEMA = "fixture-envelope.v1.schema.json"
_FIXTURE_KINDS = {"communications": "communication", "threats": "threat"}
_SIGNAL_CODES = {
    "active_fraud_network_link",
    "active_threat_match",
    "credential_request",
    "delivery_fee_request",
    "known_recipient_amount_outlier",
    "lookalike_domain",
    "new_recipient",
    "new_recipient_amount_outlier",
    "prize_fee_request",
    "relative_emergency_payment",
    "safe_account_transfer",
    "urgency_or_secrecy",
    "visual_brand_imitation",
}


class CatalogValidationError(ValueError):
    """A stable, non-sensitive catalog validation failure."""

    def __init__(self, code: str, resource: str, detail: str) -> None:
        self.code = code
        self.resource = resource
        self.detail = detail
        super().__init__(f"{code}: {resource}: {detail}")


class LocalCatalogLoader:
    """Load catalogs without allowing paths or references outside configured roots."""

    def __init__(
        self,
        *,
        schema_root: Path,
        content_root: Path,
        fixture_root: Path,
        policy_version: str,
    ) -> None:
        self._schema_root = schema_root.resolve()
        self._content_root = content_root.resolve()
        self._fixture_root = fixture_root.resolve()
        self._policy_version = policy_version

    def load(self) -> CatalogSnapshot:
        policy = self.load_policy()
        trusted = self.load_trusted_entities()
        fixtures = self.load_fixtures()
        digest_items = [
            policy.content_sha256,
            trusted.content_sha256,
            *(fixture.file_sha256 for fixture in fixtures),
        ]
        return CatalogSnapshot(
            policy=policy,
            trusted_entities=trusted,
            fixtures=fixtures,
            catalog_sha256=_canonical_sha256(digest_items),
        )

    def load_policy(self) -> PolicySnapshot:
        resource = f"policies/{self._policy_version}.json"
        document = self._load_document(
            self._content_root,
            resource,
            schema_name=_POLICY_SCHEMA,
        )
        _require_supported_schema(document, resource)
        policy_version = _string(document, "policy_version", resource)
        if policy_version != self._policy_version:
            raise CatalogValidationError(
                "unsupported_version",
                resource,
                "policy_version does not match configured version",
            )
        _verify_document_hash(document, resource)

        thresholds = _object(document, "thresholds", resource)
        low_max = _integer(thresholds, "low_max", resource)
        medium_max = _integer(thresholds, "medium_max", resource)
        high_max = _integer(thresholds, "high_max", resource)
        critical_max = _integer(thresholds, "critical_max", resource)
        if not low_max < medium_max < high_max < critical_max:
            raise CatalogValidationError(
                "invalid_policy",
                resource,
                "risk thresholds must be strictly increasing",
            )

        signals: list[SignalPolicy] = []
        signal_codes: set[str] = set()
        for item in _array(document, "signals", resource):
            signal = _as_object(item, resource)
            code = _string(signal, "code", resource)
            if code in signal_codes:
                raise CatalogValidationError(
                    "duplicate_entry", resource, "signal codes must be unique"
                )
            signal_codes.add(code)
            signals.append(
                SignalPolicy(
                    code=code,
                    group=_string(signal, "group", resource),
                    base_score=_integer(signal, "base_score", resource),
                )
            )
        if signal_codes != _SIGNAL_CODES:
            raise CatalogValidationError(
                "invalid_policy",
                resource,
                "signal catalog does not match policy schema version",
            )

        modifiers = _object(document, "modifiers", resource)
        return PolicySnapshot(
            schema_version=_string(document, "schema_version", resource),
            policy_version=policy_version,
            score_kind=_string(document, "score_kind", resource),
            thresholds=RiskThresholds(
                low_max=low_max,
                medium_max=medium_max,
                high_max=high_max,
                critical_max=critical_max,
            ),
            signals=tuple(signals),
            urgency_with_other_signal=_integer(modifiers, "urgency_with_other_signal", resource),
            linked_contact=_integer(modifiers, "linked_contact", resource),
            deduplication_key=_string(document, "deduplication_key", resource),
            max_score=_integer(document, "max_score", resource),
            content_sha256=_string(document, "content_sha256", resource),
        )

    def load_trusted_entities(self) -> TrustedEntitiesSnapshot:
        resource = f"trusted_entities/{TRUSTED_ENTITIES_FILE}"
        document = self._load_document(
            self._content_root,
            resource,
            schema_name=_TRUSTED_SCHEMA,
        )
        _require_supported_schema(document, resource)
        _verify_document_hash(document, resource)

        entities: list[TrustedEntity] = []
        codes: set[str] = set()
        identities: set[tuple[str, str]] = set()
        for item in _array(document, "entities", resource):
            entity = _as_object(item, resource)
            code = _string(entity, "code", resource)
            identity = (
                _string(entity, "kind", resource),
                _string(entity, "value", resource),
            )
            if code in codes or identity in identities:
                raise CatalogValidationError(
                    "duplicate_entry", resource, "trusted entities must be unique"
                )
            codes.add(code)
            identities.add(identity)
            entities.append(
                TrustedEntity(
                    code=code,
                    kind=identity[0],
                    value=identity[1],
                    status=_string(entity, "status", resource),
                )
            )

        reviewed_at = _utc_datetime(_string(document, "reviewed_at", resource), resource)
        return TrustedEntitiesSnapshot(
            schema_version=_string(document, "schema_version", resource),
            catalog_version=_string(document, "catalog_version", resource),
            source=_string(document, "source", resource),
            reviewed_at=reviewed_at,
            entities=tuple(entities),
            content_sha256=_string(document, "content_sha256", resource),
        )

    def load_fixtures(self) -> tuple[FixtureEnvelope, ...]:
        fixtures: list[FixtureEnvelope] = []
        identities: set[tuple[str, str]] = set()

        for directory_name, expected_kind in _FIXTURE_KINDS.items():
            directory = _safe_directory(self._fixture_root, directory_name)
            paths = _json_files(directory)
            if not paths:
                raise CatalogValidationError(
                    "catalog_unavailable",
                    directory_name,
                    "mandatory fixture directory has no JSON files",
                )
            for path in paths:
                resolved = _require_inside_root(path, self._fixture_root, directory_name)
                resource = resolved.relative_to(self._fixture_root).as_posix()
                document = self._load_document(
                    self._fixture_root,
                    resource,
                    schema_name=_FIXTURE_SCHEMA,
                )
                _require_supported_schema(document, resource)
                fixture_version = _string(document, "fixture_version", resource)
                if fixture_version != FIXTURE_VERSION:
                    raise CatalogValidationError(
                        "unsupported_version",
                        resource,
                        "fixture_version is not supported",
                    )
                kind = _string(document, "kind", resource)
                if kind != expected_kind:
                    raise CatalogValidationError(
                        "invalid_fixture",
                        resource,
                        "fixture kind does not match its directory",
                    )
                payload = _object(document, "payload", resource)
                if kind == "threat":
                    self._validate_schema(
                        payload,
                        resource=f"{resource}.payload",
                        schema_name="threat-record.v1.schema.json",
                    )
                elif kind == "communication":
                    self._validate_schema(
                        payload,
                        resource=f"{resource}.payload",
                        schema_name="observation.v1.schema.json",
                    )
                payload_hash = _string(document, "payload_sha256", resource)
                if _canonical_sha256(payload) != payload_hash:
                    raise CatalogValidationError(
                        "hash_mismatch", resource, "payload_sha256 does not match payload"
                    )
                fixture_id = _string(document, "fixture_id", resource)
                identity = (fixture_id, fixture_version)
                if identity in identities:
                    raise CatalogValidationError(
                        "duplicate_entry", resource, "fixture id and version must be unique"
                    )
                identities.add(identity)
                file_hash = _file_sha256(resolved)
                refs = tuple(
                    _map_reference(item, resource) for item in _array(document, "refs", resource)
                )
                fixtures.append(
                    FixtureEnvelope(
                        schema_version=_string(document, "schema_version", resource),
                        fixture_id=fixture_id,
                        fixture_version=fixture_version,
                        kind=kind,
                        locale=_string(document, "locale", resource),
                        payload=payload,
                        payload_sha256=payload_hash,
                        refs=refs,
                        source_path=resource,
                        file_sha256=file_hash,
                    )
                )
        fixtures_by_path = {fixture.source_path: fixture for fixture in fixtures}
        for fixture in fixtures:
            for reference in fixture.refs:
                _validate_reference(
                    reference,
                    owner=fixture,
                    fixture_root=self._fixture_root,
                    fixtures_by_path=fixtures_by_path,
                )
        return tuple(sorted(fixtures, key=lambda item: item.source_path))

    def _load_document(
        self,
        root: Path,
        relative_path: str,
        *,
        schema_name: str,
    ) -> dict[str, JsonValue]:
        resource = relative_path
        path = _safe_file(root, relative_path, resource)
        document = _read_json_object(path, resource)
        self._validate_schema(document, resource=resource, schema_name=schema_name)
        return document

    def _validate_schema(
        self,
        document: Mapping[str, JsonValue],
        *,
        resource: str,
        schema_name: str,
    ) -> None:
        schema_path = _safe_file(self._schema_root, schema_name, f"schemas/{schema_name}")
        schema = _read_json_object(schema_path, f"schemas/{schema_name}")
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise CatalogValidationError(
                "invalid_schema", f"schemas/{schema_name}", "JSON Schema is invalid"
            ) from exc
        errors = sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if errors:
            location = ".".join(str(part) for part in errors[0].absolute_path) or "$"
            raise CatalogValidationError(
                "schema_validation_failed",
                resource,
                f"value at {location} violates the schema",
            )


def _read_json_object(path: Path, resource: str) -> dict[str, JsonValue]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CatalogValidationError(
            "catalog_unavailable", resource, "file cannot be read"
        ) from exc
    if len(raw) > MAX_JSON_BYTES:
        raise CatalogValidationError("file_too_large", resource, "JSON file exceeds size limit")
    try:
        decoded: object = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise CatalogValidationError("invalid_json", resource, "file is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise CatalogValidationError("invalid_json", resource, "malformed JSON") from exc
    except _DuplicateKeyError as exc:
        raise CatalogValidationError("duplicate_key", resource, "JSON keys must be unique") from exc
    except _NonFiniteNumberError as exc:
        raise CatalogValidationError(
            "invalid_json", resource, "JSON numbers must be finite"
        ) from exc
    if not isinstance(decoded, dict) or any(not isinstance(key, str) for key in decoded):
        raise CatalogValidationError("invalid_json", resource, "top level must be an object")
    return cast(dict[str, JsonValue], decoded)


class _DuplicateKeyError(ValueError):
    pass


class _NonFiniteNumberError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise _NonFiniteNumberError(value)


def _safe_file(root: Path, relative_path: str, resource: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in relative_path:
        raise CatalogValidationError("unsafe_reference", resource, "path must stay within root")
    try:
        candidate = (root / Path(*relative.parts)).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CatalogValidationError(
            "catalog_unavailable", resource, "referenced file does not exist"
        ) from exc
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise CatalogValidationError("unsafe_reference", resource, "path must stay within root")
    return candidate


def _safe_directory(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    try:
        candidate = (root / Path(*relative.parts)).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CatalogValidationError(
            "catalog_unavailable", relative_path, "fixture directory does not exist"
        ) from exc
    if not candidate.is_relative_to(root) or not candidate.is_dir():
        raise CatalogValidationError(
            "unsafe_reference", relative_path, "directory must stay within fixture root"
        )
    return candidate


def _require_inside_root(path: Path, root: Path, resource: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CatalogValidationError(
            "catalog_unavailable", resource, "fixture file cannot be resolved"
        ) from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise CatalogValidationError(
            "unsafe_reference", resource, "fixture path must stay within root"
        )
    return resolved


def _json_files(directory: Path) -> tuple[Path, ...]:
    try:
        return tuple(sorted(path for path in directory.rglob("*.json") if path.is_file()))
    except OSError as exc:
        raise CatalogValidationError(
            "catalog_unavailable", directory.name, "fixture directory cannot be read"
        ) from exc


def _require_supported_schema(document: Mapping[str, JsonValue], resource: str) -> None:
    version = document.get("schema_version")
    if version != SCHEMA_VERSION:
        raise CatalogValidationError(
            "unsupported_version", resource, "schema_version is not supported"
        )


def _verify_document_hash(document: dict[str, JsonValue], resource: str) -> None:
    expected = _string(document, "content_sha256", resource)
    content = {key: value for key, value in document.items() if key != "content_sha256"}
    if _canonical_sha256(content) != expected:
        raise CatalogValidationError(
            "hash_mismatch", resource, "content_sha256 does not match document"
        )


def _canonical_sha256(value: JsonValue | Sequence[str] | Mapping[str, JsonValue]) -> str:
    try:
        canonical = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("catalog value must contain finite JSON") from exc
    return hashlib.sha256(canonical).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CatalogValidationError(
            "catalog_unavailable", path.name, "file cannot be read"
        ) from exc


def _map_reference(value: JsonValue, resource: str) -> FixtureReference:
    reference = _as_object(value, resource)
    return FixtureReference(
        path=_string(reference, "path", resource),
        sha256=_string(reference, "sha256", resource),
        fixture_id=_string(reference, "fixture_id", resource),
        fixture_version=_string(reference, "fixture_version", resource),
    )


def _validate_reference(
    reference: FixtureReference,
    *,
    owner: FixtureEnvelope,
    fixture_root: Path,
    fixtures_by_path: Mapping[str, FixtureEnvelope],
) -> None:
    relative = PurePosixPath(reference.path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in reference.path:
        raise CatalogValidationError(
            "unsafe_reference", owner.source_path, "fixture reference escapes root"
        )
    target_path = _safe_file(fixture_root, reference.path, owner.source_path)
    target = fixtures_by_path.get(reference.path)
    if target is None:
        raise CatalogValidationError(
            "invalid_reference", owner.source_path, "reference is outside the fixture catalog"
        )
    if owner.source_path == reference.path:
        raise CatalogValidationError(
            "invalid_reference", owner.source_path, "fixture cannot reference itself"
        )
    if _file_sha256(target_path) != reference.sha256:
        raise CatalogValidationError(
            "hash_mismatch", owner.source_path, "referenced fixture hash does not match"
        )
    if (
        target.fixture_id != reference.fixture_id
        or target.fixture_version != reference.fixture_version
    ):
        raise CatalogValidationError(
            "invalid_reference", owner.source_path, "referenced fixture identity does not match"
        )


def _object(document: Mapping[str, JsonValue], key: str, resource: str) -> dict[str, JsonValue]:
    return _as_object(document.get(key), resource)


def _as_object(value: JsonValue | None, resource: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise CatalogValidationError("invalid_catalog", resource, "expected an object")
    return value


def _array(document: Mapping[str, JsonValue], key: str, resource: str) -> list[JsonValue]:
    value = document.get(key)
    if not isinstance(value, list):
        raise CatalogValidationError("invalid_catalog", resource, "expected an array")
    return value


def _string(document: Mapping[str, JsonValue], key: str, resource: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        raise CatalogValidationError("invalid_catalog", resource, f"{key} must be a string")
    return value


def _integer(document: Mapping[str, JsonValue], key: str, resource: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CatalogValidationError("invalid_catalog", resource, f"{key} must be an integer")
    return value


def _utc_datetime(value: str, resource: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogValidationError(
            "invalid_catalog", resource, "reviewed_at must be an RFC 3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise CatalogValidationError("invalid_catalog", resource, "reviewed_at must be in UTC")
    return parsed
