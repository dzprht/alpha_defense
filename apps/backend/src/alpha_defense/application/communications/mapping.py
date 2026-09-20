"""Canonical raw payload mapping shared by communication use cases and adapters."""

from __future__ import annotations

import hashlib
import json

from alpha_defense.application.ports.events import JsonObject, JsonValue
from alpha_defense.domain.communications import (
    CallTranscriptPayload,
    MessengerPayload,
    ObservationPayload,
    SmsPayload,
    WebResourcePayload,
)


def payload_to_data(payload: ObservationPayload) -> JsonObject:
    if isinstance(payload, (SmsPayload, MessengerPayload)):
        return {
            "text": payload.text,
            "sender": payload.sender,
            "conversation_id": payload.conversation_id,
        }
    if isinstance(payload, CallTranscriptPayload):
        segments: list[JsonValue] = [
            {
                "sequence": segment.sequence,
                "text": segment.text,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
            }
            for segment in payload.segments
        ]
        return {
            "transcript": payload.transcript,
            "phone": payload.phone,
            "call_id": payload.call_id,
            "sequence": payload.sequence,
            "segments": segments,
        }
    if isinstance(payload, WebResourcePayload):
        return {
            "url": payload.url,
            "media_id": None if payload.media_id is None else str(payload.media_id),
        }
    raise TypeError("unsupported observation payload")


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
