"""Immutable communication evidence and raw content references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TypeAlias

from alpha_defense.domain.communications.normalization import (
    MAX_INDICATORS,
    NORMALIZATION_VERSION,
    NormalizedIndicator,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SOURCE = re.compile(r"^[a-z][a-z0-9.-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ObservationKind(StrEnum):
    SMS = "sms"
    MESSENGER = "messenger"
    CALL_TRANSCRIPT = "call_transcript"
    WEB_RESOURCE = "web_resource"


@dataclass(frozen=True, slots=True)
class SmsPayload:
    text: str
    sender: str
    conversation_id: str
    kind: ObservationKind = ObservationKind.SMS

    def __post_init__(self) -> None:
        _require_text(self.text, field_name="text", max_length=10_000)
        _require_text(self.sender, field_name="sender", max_length=256, require_trimmed=True)
        _require_stable_id(self.conversation_id, field_name="conversation_id")


@dataclass(frozen=True, slots=True)
class MessengerPayload:
    text: str
    sender: str
    conversation_id: str
    kind: ObservationKind = ObservationKind.MESSENGER

    def __post_init__(self) -> None:
        _require_text(self.text, field_name="text", max_length=10_000)
        _require_text(self.sender, field_name="sender", max_length=256, require_trimmed=True)
        _require_stable_id(self.conversation_id, field_name="conversation_id")


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    sequence: int
    text: str
    start_ms: int | None = None
    end_ms: int | None = None

    def __post_init__(self) -> None:
        _require_non_negative_int(self.sequence, field_name="sequence")
        _require_text(self.text, field_name="text", max_length=10_000)
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("segment start_ms and end_ms must be provided together")
        if self.start_ms is not None and self.end_ms is not None:
            _require_non_negative_int(self.start_ms, field_name="start_ms")
            _require_non_negative_int(self.end_ms, field_name="end_ms")
            if self.end_ms <= self.start_ms:
                raise ValueError("segment end_ms must be later than start_ms")


@dataclass(frozen=True, slots=True)
class CallTranscriptPayload:
    transcript: str
    phone: str
    call_id: str
    sequence: int
    segments: tuple[TranscriptSegment, ...] = ()
    kind: ObservationKind = ObservationKind.CALL_TRANSCRIPT

    def __post_init__(self) -> None:
        _require_text(self.transcript, field_name="transcript", max_length=30_000)
        _require_text(self.phone, field_name="phone", max_length=256, require_trimmed=True)
        _require_stable_id(self.call_id, field_name="call_id")
        _require_non_negative_int(self.sequence, field_name="sequence")
        if not isinstance(self.segments, tuple):
            raise TypeError("segments must be a tuple")
        if len(self.segments) > 200:
            raise ValueError("call transcript cannot contain more than 200 segments")
        if any(not isinstance(segment, TranscriptSegment) for segment in self.segments):
            raise TypeError("segments must contain TranscriptSegment values")
        sequences = tuple(segment.sequence for segment in self.segments)
        if sequences != tuple(sorted(set(sequences))):
            raise ValueError("segment sequence values must be strictly increasing")
        if sum(len(segment.text) for segment in self.segments) > 30_000:
            raise ValueError("segment text exceeds the transcript limit")


@dataclass(frozen=True, slots=True)
class WebResourcePayload:
    url: str | None = None
    media_id: EntityId | None = None
    kind: ObservationKind = ObservationKind.WEB_RESOURCE

    def __post_init__(self) -> None:
        if self.url is None and self.media_id is None:
            raise ValueError("web resource requires url or media_id")
        if self.url is not None:
            _require_text(self.url, field_name="url", max_length=2048, require_trimmed=True)
        if self.media_id is not None and not isinstance(self.media_id, EntityId):
            raise TypeError("media_id must be an EntityId or None")


ObservationPayload: TypeAlias = (
    SmsPayload | MessengerPayload | CallTranscriptPayload | WebResourcePayload
)


@dataclass(frozen=True, slots=True)
class ObservationContent:
    content_ref: EntityId
    observation_id: EntityId
    payload: ObservationPayload
    content_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.content_ref, EntityId):
            raise TypeError("content_ref must be an EntityId")
        if not isinstance(self.observation_id, EntityId):
            raise TypeError("observation_id must be an EntityId")
        if not isinstance(
            self.payload,
            (SmsPayload, MessengerPayload, CallTranscriptPayload, WebResourcePayload),
        ):
            raise TypeError("payload must be an observation payload")
        if not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: EntityId
    owner_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    kind: ObservationKind
    source: str
    source_event_id: str
    source_event_fingerprint: str
    occurred_at: datetime
    received_at: datetime
    content_ref: EntityId
    normalized_indicators: tuple[NormalizedIndicator, ...]
    media_refs: tuple[EntityId, ...]
    execution_mode: ExecutionMode
    conversation_id: str | None = None
    call_id: str | None = None
    sequence: int | None = None
    normalization_version: str = NORMALIZATION_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "observation_id",
            "owner_id",
            "session_id",
            "namespace_id",
            "content_ref",
        ):
            if not isinstance(getattr(self, field_name), EntityId):
                raise TypeError(f"{field_name} must be an EntityId")
        if not isinstance(self.kind, ObservationKind):
            raise TypeError("kind must be an ObservationKind")
        if not _SOURCE.fullmatch(self.source):
            raise ValueError("source must use the stable source format")
        _require_stable_id(self.source_event_id, field_name="source_event_id")
        if not _SHA256.fullmatch(self.source_event_fingerprint):
            raise ValueError("source_event_fingerprint must be a lowercase SHA-256 digest")
        _require_utc(self.occurred_at, field_name="occurred_at")
        _require_utc(self.received_at, field_name="received_at")
        if self.occurred_at > self.received_at + timedelta(minutes=5):
            raise ValueError("occurred_at cannot be more than five minutes in the future")
        if self.normalization_version != NORMALIZATION_VERSION:
            raise ValueError("normalization_version is not supported")
        if not isinstance(self.normalized_indicators, tuple):
            raise TypeError("normalized_indicators must be a tuple")
        if len(self.normalized_indicators) > MAX_INDICATORS:
            raise ValueError(f"observation cannot have more than {MAX_INDICATORS} indicators")
        if any(
            not isinstance(indicator, NormalizedIndicator)
            or indicator.normalization_version != self.normalization_version
            for indicator in self.normalized_indicators
        ):
            raise ValueError("normalized indicators must use the observation version")
        if not isinstance(self.media_refs, tuple) or any(
            not isinstance(media_id, EntityId) for media_id in self.media_refs
        ):
            raise TypeError("media_refs must contain EntityId values")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        self._validate_correlation_fields()

    def _validate_correlation_fields(self) -> None:
        if self.kind in {ObservationKind.SMS, ObservationKind.MESSENGER}:
            if (
                self.conversation_id is None
                or self.call_id is not None
                or self.sequence is not None
            ):
                raise ValueError("text observations require only conversation_id")
            _require_stable_id(self.conversation_id, field_name="conversation_id")
            return
        if self.kind is ObservationKind.CALL_TRANSCRIPT:
            if self.call_id is None or self.sequence is None or self.conversation_id is not None:
                raise ValueError("call observations require call_id and sequence")
            _require_stable_id(self.call_id, field_name="call_id")
            _require_non_negative_int(self.sequence, field_name="sequence")
            return
        if any(value is not None for value in (self.conversation_id, self.call_id, self.sequence)):
            raise ValueError("web observations cannot have conversation or call fields")


@dataclass(frozen=True, slots=True)
class StoredObservation:
    observation: Observation
    content: ObservationContent

    def __post_init__(self) -> None:
        if not isinstance(self.observation, Observation):
            raise TypeError("observation must be an Observation")
        if not isinstance(self.content, ObservationContent):
            raise TypeError("content must be an ObservationContent")
        if self.content.observation_id != self.observation.observation_id:
            raise ValueError("content observation_id does not match observation")
        if self.content.content_ref != self.observation.content_ref:
            raise ValueError("content_ref does not match observation")
        if self.content.payload.kind is not self.observation.kind:
            raise ValueError("content kind does not match observation")


def _require_text(
    value: str,
    *,
    field_name: str,
    max_length: int,
    require_trimmed: bool = False,
) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip() or len(value) > max_length:
        raise ValueError(f"{field_name} must contain 1..{max_length} characters")
    if require_trimmed and value != value.strip():
        raise ValueError(f"{field_name} must be trimmed")


def _require_stable_id(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not _STABLE_ID.fullmatch(value):
        raise ValueError(f"{field_name} must use the stable identifier format")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_utc(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC-aware")
