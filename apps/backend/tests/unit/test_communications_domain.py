"""Domain rules for communication variants and versioned normalization."""

from __future__ import annotations

from uuid import UUID

import pytest

from alpha_defense.domain.communications import (
    CallTranscriptPayload,
    CommunicationIndicatorType,
    IndicatorOrigin,
    NormalizationStatus,
    SmsPayload,
    TranscriptSegment,
    WebResourcePayload,
    indicators_from_resource,
    indicators_from_text,
    normalize_candidate,
)
from alpha_defense.domain.shared import EntityId


def test_phone_normalization_keeps_invalid_input_explicit() -> None:
    valid = normalize_candidate(
        CommunicationIndicatorType.PHONE,
        "+7 (999) 123-45-67",
        origin=IndicatorOrigin.CALLER,
    )
    invalid = normalize_candidate(
        CommunicationIndicatorType.PHONE,
        "ALFA-DEMO",
        origin=IndicatorOrigin.SENDER,
    )

    assert valid.normalized_value == "+79991234567"
    assert valid.status is NormalizationStatus.NORMALIZED
    assert invalid.raw_value == "ALFA-DEMO"
    assert invalid.normalized_value is None
    assert invalid.status is NormalizationStatus.INVALID


def test_url_normalization_preserves_path_and_query_but_drops_fragment() -> None:
    indicators = indicators_from_resource("HTTPS://ExAmPle.TEST/Pay/Step?order=42&next=yes#private")

    assert [item.indicator_type for item in indicators] == [
        CommunicationIndicatorType.URL,
        CommunicationIndicatorType.DOMAIN,
    ]
    assert indicators[0].normalized_value == "https://example.test/Pay/Step?order=42&next=yes"
    assert indicators[1].normalized_value == "example.test"


def test_ip_url_does_not_create_a_fake_domain_indicator() -> None:
    indicators = indicators_from_resource("https://192.0.2.10/path?x=1")

    assert len(indicators) == 1
    assert indicators[0].indicator_type is CommunicationIndicatorType.URL
    assert indicators[0].normalized_value == "https://192.0.2.10/path?x=1"


def test_payload_limits_and_call_segment_order_are_enforced() -> None:
    with pytest.raises(ValueError, match="text must contain"):
        SmsPayload(text="   ", sender="ALFA-DEMO", conversation_id="conversation-1")
    with pytest.raises(ValueError, match="strictly increasing"):
        CallTranscriptPayload(
            transcript="Текст разговора",
            phone="+70000000001",
            call_id="call-1",
            sequence=0,
            segments=(
                TranscriptSegment(sequence=2, text="Второй"),
                TranscriptSegment(sequence=1, text="Первый"),
            ),
        )
    with pytest.raises(ValueError, match="url or media_id"):
        WebResourcePayload()

    media_only = WebResourcePayload(media_id=EntityId(UUID(int=10)))
    assert media_only.url is None


def test_text_extraction_deduplicates_the_same_embedded_url() -> None:
    indicators = indicators_from_text(
        "Откройте https://example.test/a?x=1 и https://example.test/a?x=1.",
        sender="ALFA-DEMO",
    )

    assert len(indicators) == 3
    assert indicators[0].status is NormalizationStatus.INVALID
    assert [item.normalized_value for item in indicators[1:]] == [
        "https://example.test/a?x=1",
        "example.test",
    ]


def test_indicator_limit_is_rejected_instead_of_silently_truncated() -> None:
    text = " ".join(f"https://example.test/{index}" for index in range(26))

    with pytest.raises(ValueError, match="more than 50"):
        indicators_from_text(text, sender="ALFA-DEMO")
