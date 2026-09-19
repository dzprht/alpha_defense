"""Threat feed adapter over the validated synthetic fixture catalog."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from alpha_defense.application.ports import (
    CatalogLoaderPort,
    JsonValue,
    ThreatBatch,
    ThreatFeedRecord,
    ThreatFeedUnavailableError,
)


class FixtureThreatFeed:
    def __init__(self, catalog: CatalogLoaderPort) -> None:
        self._catalog = catalog

    def fetch(self, source: str) -> ThreatBatch:
        try:
            catalog = self._catalog.load()
            payloads = tuple(
                fixture.payload
                for fixture in catalog.fixtures
                if fixture.kind == "threat" and fixture.payload.get("source") == source
            )
            if not payloads:
                raise ValueError("configured threat source has no records")
            versions = {_string(payload, "source_version") for payload in payloads}
            valid_until_values = {_timestamp(payload, "feed_valid_until") for payload in payloads}
            if len(versions) != 1 or len(valid_until_values) != 1:
                raise ValueError("threat batch metadata is inconsistent")
            records = tuple(_record(payload) for payload in payloads)
            return ThreatBatch(
                source=source,
                source_version=versions.pop(),
                generated_at=max(record.observed_at for record in records),
                valid_until=valid_until_values.pop(),
                records=records,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise ThreatFeedUnavailableError("fixture threat feed is unavailable") from exc


def _record(payload: Mapping[str, JsonValue]) -> ThreatFeedRecord:
    return ThreatFeedRecord(
        source_record_id=_string(payload, "source_record_id"),
        indicator_type=_string(payload, "indicator_type"),
        value=_string(payload, "normalized_value"),
        normalization_version=_string(payload, "normalization_version"),
        status=_string(payload, "status"),
        first_seen_at=_timestamp(payload, "first_seen_at"),
        observed_at=_timestamp(payload, "observed_at"),
        expires_at=_timestamp(payload, "expires_at"),
        evidence_ref=_string(payload, "evidence_ref"),
        verification_source=_string(payload, "verification_source"),
    )


def _string(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _timestamp(payload: Mapping[str, JsonValue], key: str) -> datetime:
    value = _string(payload, key)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{key} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{key} must be in UTC")
    return parsed
