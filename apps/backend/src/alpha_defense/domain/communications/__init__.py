"""Communication observation domain."""

from alpha_defense.domain.communications.normalization import (
    MAX_INDICATORS,
    NORMALIZATION_VERSION,
    CommunicationIndicatorType,
    IndicatorOrigin,
    NormalizationStatus,
    NormalizedIndicator,
    indicators_from_resource,
    indicators_from_text,
    normalize_candidate,
    normalize_value,
)
from alpha_defense.domain.communications.observation import (
    CallTranscriptPayload,
    MessengerPayload,
    Observation,
    ObservationContent,
    ObservationKind,
    ObservationPayload,
    SmsPayload,
    StoredObservation,
    TranscriptSegment,
    WebResourcePayload,
)

__all__ = [
    "MAX_INDICATORS",
    "NORMALIZATION_VERSION",
    "CallTranscriptPayload",
    "CommunicationIndicatorType",
    "IndicatorOrigin",
    "MessengerPayload",
    "NormalizationStatus",
    "NormalizedIndicator",
    "Observation",
    "ObservationContent",
    "ObservationKind",
    "ObservationPayload",
    "SmsPayload",
    "StoredObservation",
    "TranscriptSegment",
    "WebResourcePayload",
    "indicators_from_resource",
    "indicators_from_text",
    "normalize_candidate",
    "normalize_value",
]
