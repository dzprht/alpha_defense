"""Plain contracts for validated versioned catalogs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from alpha_defense.application.ports.events import JsonValue
from alpha_defense.domain.education import EducationCard, GuidanceCatalog


@dataclass(frozen=True, slots=True)
class RiskThresholds:
    low_max: int
    medium_max: int
    high_max: int
    critical_max: int


@dataclass(frozen=True, slots=True)
class SignalPolicy:
    code: str
    group: str
    base_score: int


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    schema_version: str
    policy_version: str
    score_kind: str
    thresholds: RiskThresholds
    signals: tuple[SignalPolicy, ...]
    urgency_with_other_signal: int
    linked_contact: int
    deduplication_key: str
    max_score: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class TrustedEntity:
    code: str
    kind: str
    value: str
    status: str


@dataclass(frozen=True, slots=True)
class TrustedEntitiesSnapshot:
    schema_version: str
    catalog_version: str
    source: str
    reviewed_at: datetime
    entities: tuple[TrustedEntity, ...]
    content_sha256: str


@dataclass(frozen=True, slots=True)
class EducationCatalogSnapshot:
    locale: str
    cards: tuple[EducationCard, ...]
    content_sha256: str


@dataclass(frozen=True, slots=True)
class FixtureReference:
    path: str
    sha256: str
    fixture_id: str
    fixture_version: str


@dataclass(frozen=True, slots=True)
class FixtureEnvelope:
    schema_version: str
    fixture_id: str
    fixture_version: str
    kind: str
    locale: str
    payload: Mapping[str, JsonValue]
    payload_sha256: str
    refs: tuple[FixtureReference, ...]
    source_path: str
    file_sha256: str


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    policy: PolicySnapshot
    trusted_entities: TrustedEntitiesSnapshot
    fixtures: tuple[FixtureEnvelope, ...]
    catalog_sha256: str
    guidance: GuidanceCatalog | None = None
    education: EducationCatalogSnapshot | None = None


class CatalogLoaderPort(Protocol):
    """Load one fully validated plain view of mandatory local catalogs."""

    def load(self) -> CatalogSnapshot: ...


class ContentCatalogPort(Protocol):
    """Read reviewed guidance and education content with deterministic fallback."""

    def load_guidance(self, locale: str) -> GuidanceCatalog: ...

    def load_education(self, locale: str) -> EducationCatalogSnapshot: ...

    def get_education_card(
        self,
        code: str,
        locale: str,
        version: str | None = None,
    ) -> EducationCard | None: ...

    def trusted_support_contact(self) -> TrustedEntity | None: ...
