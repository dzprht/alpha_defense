"""Immutable registry snapshots and publication invariants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats.indicator import ThreatIndicator
from alpha_defense.domain.threats.threat_record import ThreatRecord, _require_utc

_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_SEMVER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True, order=True)
class SourceVersion:
    source: str
    version: str

    def __post_init__(self) -> None:
        if not _VERSION_PATTERN.fullmatch(self.source):
            raise ValueError("source must use the stable source format")
        if not _SEMVER_PATTERN.fullmatch(self.version):
            raise ValueError("source version must be semantic x.y.z")

    @property
    def precedence(self) -> tuple[int, int, int]:
        match = _SEMVER_PATTERN.fullmatch(self.version)
        if match is None:  # pragma: no cover - guarded by construction
            raise RuntimeError("source version invariant was broken")
        major, minor, patch = match.groups()
        return int(major), int(minor), int(patch)


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    snapshot_id: EntityId
    version: str
    source_versions: tuple[SourceVersion, ...]
    published_at: datetime
    valid_until: datetime
    records: tuple[ThreatRecord, ...]
    content_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, EntityId):
            raise TypeError("snapshot_id must be an EntityId")
        if not _VERSION_PATTERN.fullmatch(self.version):
            raise ValueError("version must use the stable registry format")
        if not self.source_versions or any(
            not isinstance(item, SourceVersion) for item in self.source_versions
        ):
            raise ValueError("source_versions must contain SourceVersion values")
        if tuple(sorted(self.source_versions)) != self.source_versions:
            raise ValueError("source_versions must be sorted")
        if len({item.source for item in self.source_versions}) != len(self.source_versions):
            raise ValueError("source_versions must contain unique sources")
        _require_utc(self.published_at, field_name="published_at")
        _require_utc(self.valid_until, field_name="valid_until")
        if self.valid_until <= self.published_at:
            raise ValueError("valid_until must be later than published_at")
        if any(not isinstance(record, ThreatRecord) for record in self.records):
            raise TypeError("records must contain ThreatRecord values")
        sources = {item.source for item in self.source_versions}
        identities: set[tuple[str, str]] = set()
        match_keys: set[tuple[str, ThreatIndicator]] = set()
        for record in self.records:
            if record.source not in sources:
                raise ValueError("record source is absent from source_versions")
            if record.observed_at > self.published_at:
                raise ValueError("record observation cannot be in the snapshot future")
            identity = (record.source, record.source_record_id)
            match_key = (record.source, record.indicator)
            if identity in identities or match_key in match_keys:
                raise ValueError("snapshot records must be unique by source identity and indicator")
            identities.add(identity)
            match_keys.add(match_key)
        if not _DIGEST_PATTERN.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a lowercase SHA-256 digest")

    @property
    def record_count(self) -> int:
        return len(self.records)

    def is_available_at(self, now: datetime) -> bool:
        _require_utc(now, field_name="now")
        return now < self.valid_until

    def active_matches(
        self,
        indicator: ThreatIndicator,
        *,
        now: datetime,
    ) -> tuple[ThreatRecord, ...]:
        _require_utc(now, field_name="now")
        return tuple(
            record
            for record in self.records
            if record.indicator == indicator and record.is_active_at(now)
        )

    def has_same_content(self, other: RegistrySnapshot) -> bool:
        return (
            self.version == other.version
            and self.source_versions == other.source_versions
            and self.valid_until == other.valid_until
            and self.records == other.records
            and self.content_sha256 == other.content_sha256
        )
