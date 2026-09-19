"""Threat indicator and record invariants without feed or persistence dependencies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from alpha_defense.domain.threats import (
    IndicatorType,
    ThreatIndicator,
    ThreatRecord,
    ThreatRecordStatus,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("indicator_type", "raw", "expected"),
    [
        (IndicatorType.DOMAIN, "Example.Test.", "example.test"),
        (IndicatorType.URL, "HTTPS://Example.Test:443", "https://example.test/"),
        (IndicatorType.PHONE, "00 7 (000) 000-00-01", "+70000000001"),
        (IndicatorType.IP, "2001:0db8::1", "2001:db8::1"),
        (IndicatorType.PATTERN_ID, "Urgency.V1", "urgency.v1"),
    ],
)
def test_typed_indicators_are_normalized_deterministically(
    indicator_type: IndicatorType,
    raw: str,
    expected: str,
) -> None:
    indicator = ThreatIndicator.from_raw(indicator_type, raw)

    assert indicator.normalized_value == expected
    assert (
        ThreatIndicator(
            indicator_type=indicator_type,
            normalized_value=expected,
        )
        == indicator
    )


@pytest.mark.parametrize(
    ("indicator_type", "value"),
    [
        (IndicatorType.DOMAIN, "localhost"),
        (IndicatorType.URL, "file:///etc/passwd"),
        (IndicatorType.PHONE, "8 900 000 00 00"),
        (IndicatorType.ACCOUNT_TOKEN, "token with spaces"),
    ],
)
def test_invalid_indicator_formats_are_rejected(
    indicator_type: IndicatorType,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        ThreatIndicator.from_raw(indicator_type, value)


def test_active_record_becomes_effectively_expired_without_mutation() -> None:
    record = ThreatRecord(
        source="alpha-defense-synthetic",
        source_record_id="record-001",
        indicator=ThreatIndicator.from_raw(IndicatorType.DOMAIN, "fraud.test"),
        status=ThreatRecordStatus.ACTIVE,
        first_seen_at=NOW - timedelta(days=2),
        observed_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(hours=1),
        evidence_ref="synthetic://threats/record-001",
        verification_source="synthetic_review",
    )

    assert record.is_active_at(NOW)
    assert record.effective_status_at(NOW + timedelta(hours=1)) is ThreatRecordStatus.EXPIRED
    assert record.status is ThreatRecordStatus.ACTIVE
