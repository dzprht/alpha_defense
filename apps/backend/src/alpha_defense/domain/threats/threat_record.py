"""Threat record lifecycle independent from feed and storage adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from alpha_defense.domain.threats.indicator import ThreatIndicator

_SOURCE_PATTERN = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")
_RECORD_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_VERIFICATION_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")


class ThreatRecordStatus(StrEnum):
    UNVERIFIED = "unverified"
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class ThreatRecord:
    source: str
    source_record_id: str
    indicator: ThreatIndicator
    status: ThreatRecordStatus
    first_seen_at: datetime
    observed_at: datetime
    expires_at: datetime
    evidence_ref: str
    verification_source: str

    def __post_init__(self) -> None:
        if not _SOURCE_PATTERN.fullmatch(self.source):
            raise ValueError("source must use the stable source format")
        if not _RECORD_ID_PATTERN.fullmatch(self.source_record_id):
            raise ValueError("source_record_id must use the stable record format")
        if not isinstance(self.indicator, ThreatIndicator):
            raise TypeError("indicator must be a ThreatIndicator")
        if not isinstance(self.status, ThreatRecordStatus):
            raise TypeError("status must be a ThreatRecordStatus")
        for field_name in ("first_seen_at", "observed_at", "expires_at"):
            _require_utc(getattr(self, field_name), field_name=field_name)
        if self.observed_at < self.first_seen_at:
            raise ValueError("observed_at must not precede first_seen_at")
        if self.expires_at <= self.first_seen_at:
            raise ValueError("expires_at must be later than first_seen_at")
        if self.status is ThreatRecordStatus.ACTIVE and self.expires_at <= self.observed_at:
            raise ValueError("active record must be valid when observed")
        if self.status is ThreatRecordStatus.EXPIRED and self.expires_at > self.observed_at:
            raise ValueError("expired record must be expired when observed")
        if (
            not isinstance(self.evidence_ref, str)
            or not self.evidence_ref
            or self.evidence_ref != self.evidence_ref.strip()
            or len(self.evidence_ref) > 512
            or "://" not in self.evidence_ref
        ):
            raise ValueError("evidence_ref must be a bounded absolute reference")
        if not _VERIFICATION_PATTERN.fullmatch(self.verification_source):
            raise ValueError("verification_source must use the stable code format")

    def effective_status_at(self, now: datetime) -> ThreatRecordStatus:
        _require_utc(now, field_name="now")
        if self.status is ThreatRecordStatus.ACTIVE and now >= self.expires_at:
            return ThreatRecordStatus.EXPIRED
        return self.status

    def is_active_at(self, now: datetime) -> bool:
        return self.effective_status_at(now) is ThreatRecordStatus.ACTIVE


def _require_utc(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC-aware")
