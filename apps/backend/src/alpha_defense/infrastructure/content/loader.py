"""Strict local loaders for versioned policies, trusted data, and fixtures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from alpha_defense.application.ports import (
    CatalogSnapshot,
    EducationCatalogSnapshot,
    FixtureEnvelope,
    FixtureReference,
    JsonValue,
    PolicySnapshot,
    RiskThresholds,
    SignalPolicy,
    TrustedEntitiesSnapshot,
    TrustedEntity,
)
from alpha_defense.domain.education import (
    ClassificationCopy,
    CompletenessCopy,
    EducationCard,
    GuidanceCatalog,
    GuidanceCompleteness,
    Recommendation,
)
from alpha_defense.domain.shared import Severity

SCHEMA_VERSION = "1.0"
FIXTURE_VERSION = "1.0.0"
TRUSTED_ENTITIES_FILE = "demo-trusted-entities-v1.json"
MAX_JSON_BYTES = 1_048_576
MAX_MARKDOWN_BYTES = 65_536
DEFAULT_LOCALE = "ru-RU"
GUIDANCE_FILES = {
    "demo-risk-v1": "demo-guidance-ru-v1.json",
    "demo-risk-v2": "demo-guidance-ru-v2.json",
}

_POLICY_SCHEMA = "policy.v1.schema.json"
_TRUSTED_SCHEMA = "trusted-entities.v1.schema.json"
_FIXTURE_SCHEMA = "fixture-envelope.v1.schema.json"
_GUIDANCE_SCHEMA = "recommendations.v1.schema.json"
_EDUCATION_CARD_SCHEMA = "education-card.v1.schema.json"
_FIXTURE_KINDS = {"communications": "communication", "threats": "threat"}
_SIGNAL_CODES_V1 = {
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
_SIGNAL_CODES_V2 = _SIGNAL_CODES_V1 | {"ml_suspicious_text"}


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
        guidance = self.load_guidance(DEFAULT_LOCALE)
        education = self.load_education(DEFAULT_LOCALE)
        self._validate_guidance_card_references(guidance, education)
        fixtures = self.load_fixtures()
        digest_items = [
            policy.content_sha256,
            trusted.content_sha256,
            guidance.content_sha256,
            education.content_sha256,
            *(fixture.file_sha256 for fixture in fixtures),
        ]
        return CatalogSnapshot(
            policy=policy,
            trusted_entities=trusted,
            guidance=guidance,
            education=education,
            fixtures=fixtures,
            catalog_sha256=_canonical_sha256(digest_items),
        )

    def load_guidance(self, locale: str) -> GuidanceCatalog:
        """Load reviewed Russian copy, falling back explicitly for other locales."""

        _require_locale(locale)
        try:
            return self._load_guidance()
        except CatalogValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise CatalogValidationError(
                "invalid_catalog",
                f"recommendations/{self._guidance_file()}",
                "guidance domain invariants are not satisfied",
            ) from exc

    def _load_guidance(self) -> GuidanceCatalog:
        resource = f"recommendations/{self._guidance_file()}"
        document = self._load_document(
            self._content_root,
            resource,
            schema_name=_GUIDANCE_SCHEMA,
        )
        _require_supported_schema(document, resource)
        _verify_document_hash(document, resource)
        classifications = tuple(
            ClassificationCopy(
                severity=Severity(_string(item_object, "severity", resource)),
                risk_label=_string(item_object, "risk_label", resource),
                explanation=_string(item_object, "explanation", resource),
            )
            for item_object in (
                _as_object(item, resource) for item in _array(document, "classifications", resource)
            )
        )
        completeness_copies = tuple(
            CompletenessCopy(
                completeness=GuidanceCompleteness(_string(item_object, "completeness", resource)),
                explanation=_string(item_object, "explanation", resource),
            )
            for item_object in (
                _as_object(item, resource) for item in _array(document, "completeness", resource)
            )
        )
        recommendations = tuple(
            Recommendation(
                code=_string(item_object, "code", resource),
                title=_string(item_object, "title", resource),
                body=_string(item_object, "body", resource),
                reason_codes=_string_tuple(item_object, "reason_codes", resource),
                education_card_codes=_string_tuple(
                    item_object,
                    "education_card_codes",
                    resource,
                ),
                uses_trusted_support_contact=_boolean(
                    item_object,
                    "uses_trusted_support_contact",
                    resource,
                ),
            )
            for item_object in (
                _as_object(item, resource) for item in _array(document, "recommendations", resource)
            )
        )
        selection = _object(document, "selection", resource)
        support = _object(document, "support", resource)
        return GuidanceCatalog(
            catalog_version=_string(document, "catalog_version", resource),
            locale=_string(document, "locale", resource),
            reviewed_at=_utc_datetime(_string(document, "reviewed_at", resource), resource),
            classifications=classifications,
            completeness_copies=completeness_copies,
            recommendations=recommendations,
            default_recommendation_code=_string(selection, "default", resource),
            unsupported_reason_recommendation_code=_string(
                selection,
                "unsupported_reason",
                resource,
            ),
            partial_recommendation_code=_string(selection, "partial", resource),
            unavailable_recommendation_code=_string(selection, "unavailable", resource),
            support_with_contact=_string(support, "with_contact", resource),
            support_without_contact=_string(support, "without_contact", resource),
            content_sha256=_string(document, "content_sha256", resource),
        )

    def load_education(self, locale: str) -> EducationCatalogSnapshot:
        """Load published cards; unsupported locales use the documented Russian fallback."""

        _require_locale(locale)
        try:
            return self._load_education()
        except CatalogValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise CatalogValidationError(
                "invalid_catalog",
                "education",
                "education domain invariants are not satisfied",
            ) from exc

    def _load_education(self) -> EducationCatalogSnapshot:
        effective_locale = DEFAULT_LOCALE
        directory = _safe_directory(self._content_root, "education")
        cards = tuple(self._load_education_card(path) for path in _markdown_files(directory))
        localized = tuple(
            sorted(
                (card for card in cards if card.locale == effective_locale),
                key=lambda card: (card.code, card.version),
            )
        )
        if not localized:
            raise CatalogValidationError(
                "catalog_unavailable",
                "education",
                "mandatory education catalog has no published cards",
            )
        identities = [(card.code, card.locale, card.version) for card in localized]
        if len(set(identities)) != len(identities):
            raise CatalogValidationError(
                "duplicate_entry",
                "education",
                "education card identities must be unique",
            )
        return EducationCatalogSnapshot(
            locale=effective_locale,
            cards=localized,
            content_sha256=_canonical_sha256([card.content_sha256 for card in localized]),
        )

    def get_education_card(
        self,
        code: str,
        locale: str,
        version: str | None = None,
    ) -> EducationCard | None:
        snapshot = self.load_education(locale)
        matches = tuple(
            card
            for card in snapshot.cards
            if card.code == code and (version is None or card.version == version)
        )
        return matches[-1] if matches else None

    def trusted_support_contact(self) -> TrustedEntity | None:
        return next(
            (
                entity
                for entity in self.load_trusted_entities().entities
                if entity.kind == "support_contact" and entity.status == "trusted"
            ),
            None,
        )

    def _load_education_card(self, path: Path) -> EducationCard:
        resolved = _require_inside_root(path, self._content_root, "education")
        resource = resolved.relative_to(self._content_root).as_posix()
        document = _read_markdown_document(resolved, resource)
        self._validate_schema(
            document,
            resource=resource,
            schema_name=_EDUCATION_CARD_SCHEMA,
        )
        _require_supported_schema(document, resource)
        _verify_document_hash(document, resource)
        return EducationCard(
            code=_string(document, "code", resource),
            locale=_string(document, "locale", resource),
            version=_string(document, "version", resource),
            title=_string(document, "title", resource),
            summary=_string(document, "summary", resource),
            body=_string(document, "body", resource),
            source_links=_string_tuple(document, "source_links", resource),
            reviewed_at=_utc_datetime(_string(document, "reviewed_at", resource), resource),
            status=_string(document, "status", resource),
            content_sha256=_string(document, "content_sha256", resource),
        )

    @staticmethod
    def _validate_guidance_card_references(
        guidance: GuidanceCatalog,
        education: EducationCatalogSnapshot,
    ) -> None:
        card_codes = {card.code for card in education.cards}
        referenced = {
            code
            for recommendation in guidance.recommendations
            for code in recommendation.education_card_codes
        }
        missing = referenced - card_codes
        if missing:
            raise CatalogValidationError(
                "invalid_reference",
                "recommendations",
                "recommendation references an unknown education card",
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
        expected_signal_codes = (
            _SIGNAL_CODES_V2 if policy_version == "demo-risk-v2" else _SIGNAL_CODES_V1
        )
        if signal_codes != expected_signal_codes:
            raise CatalogValidationError(
                "invalid_policy",
                resource,
                "signal catalog does not match policy schema version",
            )
        incomplete_low_is_unknown = document.get("incomplete_low_is_unknown", False)
        if policy_version == "demo-risk-v2" and incomplete_low_is_unknown is not True:
            raise CatalogValidationError(
                "invalid_policy", resource, "model policy must preserve unknown partial risk"
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
            incomplete_low_is_unknown=bool(incomplete_low_is_unknown),
        )

    def _guidance_file(self) -> str:
        try:
            return GUIDANCE_FILES[self._policy_version]
        except KeyError as exc:
            raise CatalogValidationError(
                "unsupported_version", "recommendations", "unknown policy guidance version"
            ) from exc

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


def _read_markdown_document(path: Path, resource: str) -> dict[str, JsonValue]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CatalogValidationError(
            "catalog_unavailable",
            resource,
            "file cannot be read",
        ) from exc
    if len(raw) > MAX_MARKDOWN_BYTES:
        raise CatalogValidationError(
            "file_too_large",
            resource,
            "Markdown file exceeds size limit",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogValidationError(
            "invalid_markdown",
            resource,
            "file is not UTF-8",
        ) from exc
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise CatalogValidationError(
            "invalid_markdown",
            resource,
            "safe front matter is required",
        )
    front_matter, separator, body = text[4:].partition("\n---\n")
    if not separator or not body.strip():
        raise CatalogValidationError(
            "invalid_markdown",
            resource,
            "front matter and body are required",
        )
    document: dict[str, JsonValue] = {}
    for line in front_matter.splitlines():
        key, delimiter, encoded_value = line.partition(":")
        if not delimiter or not key or key != key.strip() or key in document:
            raise CatalogValidationError(
                "invalid_markdown",
                resource,
                "front matter keys must be unique and unindented",
            )
        try:
            decoded = json.loads(
                encoded_value.strip(),
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, _NonFiniteNumberError) as exc:
            raise CatalogValidationError(
                "invalid_markdown",
                resource,
                "front matter values must be safe JSON literals",
            ) from exc
        if isinstance(decoded, dict):
            raise CatalogValidationError(
                "invalid_markdown",
                resource,
                "front matter objects are not supported",
            )
        document[key] = cast(JsonValue, decoded)
    document["body"] = body.strip()
    return document


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


def _markdown_files(directory: Path) -> tuple[Path, ...]:
    try:
        paths = tuple(sorted(path for path in directory.rglob("*.md") if path.is_file()))
    except OSError as exc:
        raise CatalogValidationError(
            "catalog_unavailable",
            directory.name,
            "education directory cannot be read",
        ) from exc
    if not paths:
        raise CatalogValidationError(
            "catalog_unavailable",
            directory.name,
            "mandatory education directory has no Markdown files",
        )
    return paths


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


def _boolean(document: Mapping[str, JsonValue], key: str, resource: str) -> bool:
    value = document.get(key)
    if not isinstance(value, bool):
        raise CatalogValidationError("invalid_catalog", resource, f"{key} must be a boolean")
    return value


def _string_tuple(
    document: Mapping[str, JsonValue],
    key: str,
    resource: str,
) -> tuple[str, ...]:
    values = _array(document, key, resource)
    if any(not isinstance(value, str) for value in values):
        raise CatalogValidationError(
            "invalid_catalog",
            resource,
            f"{key} must contain strings",
        )
    return tuple(cast(str, value) for value in values)


def _require_locale(locale: object) -> None:
    if not isinstance(locale, str) or not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", locale):
        raise ValueError("locale must use language-REGION format")


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
