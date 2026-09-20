"""Tagged transport and fixture contracts for all P09 observation variants."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError as PydanticValidationError

from alpha_defense.domain.communications import (
    CallTranscriptPayload,
    MessengerPayload,
    SmsPayload,
    WebResourcePayload,
)
from alpha_defense.transport.http.v1.schemas import ObservationInputSchema

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
OCCURRED_AT = "2026-09-20T10:00:00Z"


def _fixture_examples() -> tuple[dict[str, Any], ...]:
    common = {
        "source": "scenario",
        "occurred_at": OCCURRED_AT,
    }
    return (
        {
            **common,
            "kind": "sms",
            "source_event_id": "sms-1",
            "payload": {
                "text": "SMS text",
                "sender": "+70000000001",
                "conversation_id": "conversation-1",
            },
        },
        {
            **common,
            "kind": "messenger",
            "source_event_id": "chat-1",
            "payload": {
                "text": "Chat text",
                "sender": "contact-1",
                "conversation_id": "conversation-2",
            },
        },
        {
            **common,
            "kind": "call_transcript",
            "source_event_id": "call-1-part-0",
            "payload": {
                "transcript": "Call text",
                "phone": "+70000000002",
                "call_id": "call-1",
                "sequence": 0,
                "segments": [{"sequence": 0, "text": "Call", "start_ms": 0, "end_ms": 100}],
            },
        },
        {
            **common,
            "kind": "web_resource",
            "source_event_id": "web-1",
            "payload": {
                "url": "https://resource.test/path?step=1",
                "media_id": "00000000-0000-0000-0000-000000000010",
            },
        },
    )


def test_fixture_schema_accepts_all_tagged_variants() -> None:
    schema = json.loads(
        (REPOSITORY_ROOT / "contracts/fixtures/observation.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    for example in _fixture_examples():
        validator.validate(example)


def test_transport_schema_maps_all_variants_without_accepting_source() -> None:
    payload_types = (SmsPayload, MessengerPayload, CallTranscriptPayload, WebResourcePayload)

    for example, payload_type in zip(_fixture_examples(), payload_types, strict=True):
        request = dict(example)
        request.pop("source")
        parsed = ObservationInputSchema.model_validate(request).to_input()
        assert isinstance(parsed.payload, payload_type)
        assert parsed.occurred_at == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)

    with pytest.raises(PydanticValidationError):
        ObservationInputSchema.model_validate(_fixture_examples()[0])


def test_schemas_reject_unknown_fields_missing_evidence_and_oversized_text() -> None:
    sms = _fixture_examples()[0]
    sms["payload"]["unexpected"] = True
    with pytest.raises(PydanticValidationError):
        request = dict(sms)
        request.pop("source")
        ObservationInputSchema.model_validate(request)

    web = _fixture_examples()[3]
    web["payload"] = {}
    with pytest.raises(PydanticValidationError):
        request = dict(web)
        request.pop("source")
        ObservationInputSchema.model_validate(request)

    schema = json.loads(
        (REPOSITORY_ROOT / "contracts/fixtures/observation.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    oversized = _fixture_examples()[0]
    oversized["payload"]["text"] = "x" * 10_001
    errors = tuple(Draft202012Validator(schema).iter_errors(oversized))
    assert errors
