"""Communication observation use cases."""

from alpha_defense.application.communications.dto import (
    IngestObservationResult,
    ObservationInput,
    ObservationView,
)
from alpha_defense.application.communications.get_observation import GetObservation
from alpha_defense.application.communications.ingest_observation import IngestObservation
from alpha_defense.domain.communications import (
    CallTranscriptPayload,
    MessengerPayload,
    SmsPayload,
    TranscriptSegment,
    WebResourcePayload,
)
from alpha_defense.domain.shared import EntityId

__all__ = [
    "CallTranscriptPayload",
    "EntityId",
    "GetObservation",
    "IngestObservation",
    "IngestObservationResult",
    "MessengerPayload",
    "ObservationInput",
    "ObservationView",
    "SmsPayload",
    "TranscriptSegment",
    "WebResourcePayload",
]
