"""Strict request schemas prepared for the future analyze-contact workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

from alpha_defense.application.communications import (
    CallTranscriptPayload,
    EntityId,
    MessengerPayload,
    ObservationInput,
    SmsPayload,
    TranscriptSegment,
    WebResourcePayload,
)

_SOURCE_EVENT_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_CORRELATION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class _TextPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=10_000)
    sender: str = Field(min_length=1, max_length=256)
    conversation_id: str = Field(pattern=_CORRELATION_PATTERN)

    @field_validator("text")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text cannot be blank")
        return value

    @field_validator("sender")
    @classmethod
    def require_trimmed_sender(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("sender must be trimmed")
        return value


class SmsPayloadSchema(_TextPayloadSchema):
    pass


class MessengerPayloadSchema(_TextPayloadSchema):
    pass


class TranscriptSegmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=10_000)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_timing(self) -> TranscriptSegmentSchema:
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("start_ms and end_ms must be provided together")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be later than start_ms")
        if not self.text.strip():
            raise ValueError("segment text cannot be blank")
        return self


class CallTranscriptPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(min_length=1, max_length=30_000)
    phone: str = Field(min_length=1, max_length=256)
    call_id: str = Field(pattern=_CORRELATION_PATTERN)
    sequence: int = Field(ge=0)
    segments: tuple[TranscriptSegmentSchema, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def validate_transcript(self) -> CallTranscriptPayloadSchema:
        if not self.transcript.strip():
            raise ValueError("transcript cannot be blank")
        if self.phone != self.phone.strip():
            raise ValueError("phone must be trimmed")
        sequences = tuple(segment.sequence for segment in self.segments)
        if sequences != tuple(sorted(set(sequences))):
            raise ValueError("segment sequence values must be strictly increasing")
        if sum(len(segment.text) for segment in self.segments) > 30_000:
            raise ValueError("segment text exceeds the transcript limit")
        return self


class WebResourcePayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, min_length=1, max_length=2048)
    media_id: UUID | None = Field(default=None)

    @model_validator(mode="after")
    def require_evidence(self) -> WebResourcePayloadSchema:
        if self.url is None and self.media_id is None:
            raise ValueError("url or media_id is required")
        if self.url is not None and self.url != self.url.strip():
            raise ValueError("url must be trimmed")
        return self


class _ObservationInputBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_event_id: str = Field(pattern=_SOURCE_EVENT_PATTERN)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("occurred_at must be UTC-aware")
        return value


class SmsObservationInputSchema(_ObservationInputBase):
    kind: Literal["sms"]
    payload: SmsPayloadSchema


class MessengerObservationInputSchema(_ObservationInputBase):
    kind: Literal["messenger"]
    payload: MessengerPayloadSchema


class CallTranscriptObservationInputSchema(_ObservationInputBase):
    kind: Literal["call_transcript"]
    payload: CallTranscriptPayloadSchema


class WebResourceObservationInputSchema(_ObservationInputBase):
    kind: Literal["web_resource"]
    payload: WebResourcePayloadSchema


TaggedObservationInput: TypeAlias = Annotated[
    SmsObservationInputSchema
    | MessengerObservationInputSchema
    | CallTranscriptObservationInputSchema
    | WebResourceObservationInputSchema,
    Field(discriminator="kind"),
]


class ObservationInputSchema(RootModel[TaggedObservationInput]):
    def to_input(self) -> ObservationInput:
        value = self.root
        payload: SmsPayload | MessengerPayload | CallTranscriptPayload | WebResourcePayload
        if isinstance(value, SmsObservationInputSchema):
            payload = SmsPayload(**value.payload.model_dump())
        elif isinstance(value, MessengerObservationInputSchema):
            payload = MessengerPayload(**value.payload.model_dump())
        elif isinstance(value, CallTranscriptObservationInputSchema):
            payload = CallTranscriptPayload(
                transcript=value.payload.transcript,
                phone=value.payload.phone,
                call_id=value.payload.call_id,
                sequence=value.payload.sequence,
                segments=tuple(
                    TranscriptSegment(**segment.model_dump()) for segment in value.payload.segments
                ),
            )
        else:
            payload = WebResourcePayload(
                url=value.payload.url,
                media_id=(
                    None if value.payload.media_id is None else EntityId(value.payload.media_id)
                ),
            )
        return ObservationInput(
            source_event_id=value.source_event_id,
            occurred_at=value.occurred_at,
            payload=payload,
        )
