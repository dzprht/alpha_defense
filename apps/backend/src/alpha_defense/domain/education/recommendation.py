"""Published recommendation copy and deterministic guidance selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from alpha_defense.domain.shared import Severity

_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
_VERSION = re.compile(r"^[a-z0-9][a-z0-9.-]{2,63}$")


class GuidanceCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ClassificationCopy:
    severity: Severity
    risk_label: str
    explanation: str

    def __post_init__(self) -> None:
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be a Severity")
        _require_plain_text(self.risk_label, "risk_label", max_length=80)
        _require_plain_text(self.explanation, "explanation", max_length=500)


@dataclass(frozen=True, slots=True)
class CompletenessCopy:
    completeness: GuidanceCompleteness
    explanation: str

    def __post_init__(self) -> None:
        if not isinstance(self.completeness, GuidanceCompleteness):
            raise TypeError("completeness must be a GuidanceCompleteness")
        _require_plain_text(self.explanation, "explanation", max_length=500)


@dataclass(frozen=True, slots=True)
class Recommendation:
    code: str
    title: str
    body: str
    reason_codes: tuple[str, ...]
    education_card_codes: tuple[str, ...]
    uses_trusted_support_contact: bool = False

    def __post_init__(self) -> None:
        _require_code(self.code, "code")
        _require_plain_text(self.title, "title", max_length=120)
        _require_plain_text(self.body, "body", max_length=1000)
        _require_codes(self.reason_codes, "reason_codes")
        _require_codes(self.education_card_codes, "education_card_codes")
        if not isinstance(self.uses_trusted_support_contact, bool):
            raise TypeError("uses_trusted_support_contact must be a boolean")


@dataclass(frozen=True, slots=True)
class GuidanceCatalog:
    catalog_version: str
    locale: str
    reviewed_at: datetime
    classifications: tuple[ClassificationCopy, ...]
    completeness_copies: tuple[CompletenessCopy, ...]
    recommendations: tuple[Recommendation, ...]
    default_recommendation_code: str
    unsupported_reason_recommendation_code: str
    partial_recommendation_code: str
    unavailable_recommendation_code: str
    support_with_contact: str
    support_without_contact: str
    content_sha256: str

    def __post_init__(self) -> None:
        if not _VERSION.fullmatch(self.catalog_version):
            raise ValueError("catalog_version must use the stable version format")
        if not _LOCALE.fullmatch(self.locale):
            raise ValueError("locale must use language-REGION format")
        _require_utc(self.reviewed_at, "reviewed_at")
        _require_unique_enum_values(
            self.classifications,
            expected=set(Severity),
            attribute="severity",
            field_name="classifications",
        )
        _require_unique_enum_values(
            self.completeness_copies,
            expected=set(GuidanceCompleteness),
            attribute="completeness",
            field_name="completeness_copies",
        )
        if not isinstance(self.recommendations, tuple) or any(
            not isinstance(item, Recommendation) for item in self.recommendations
        ):
            raise TypeError("recommendations must contain Recommendation values")
        recommendation_codes = tuple(item.code for item in self.recommendations)
        if len(set(recommendation_codes)) != len(recommendation_codes):
            raise ValueError("recommendation codes must be unique")
        selection_codes = (
            self.default_recommendation_code,
            self.unsupported_reason_recommendation_code,
            self.partial_recommendation_code,
            self.unavailable_recommendation_code,
        )
        for code in selection_codes:
            _require_code(code, "selection code")
            if code not in recommendation_codes:
                raise ValueError("selection code must reference a recommendation")
        mapped_reasons = [
            reason
            for recommendation in self.recommendations
            for reason in recommendation.reason_codes
        ]
        if len(set(mapped_reasons)) != len(mapped_reasons):
            raise ValueError("reason codes must map to only one recommendation")
        _require_plain_text(self.support_with_contact, "support_with_contact", max_length=500)
        _require_plain_text(
            self.support_without_contact,
            "support_without_contact",
            max_length=500,
        )
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256):
            raise ValueError("content_sha256 must be a lowercase SHA-256 digest")

    def classification_for(self, severity: Severity) -> ClassificationCopy:
        return next(item for item in self.classifications if item.severity is severity)

    def completeness_for(
        self,
        completeness: GuidanceCompleteness,
    ) -> CompletenessCopy:
        return next(item for item in self.completeness_copies if item.completeness is completeness)


@dataclass(frozen=True, slots=True)
class GuidanceSelection:
    risk_label: str
    explanation: str
    recommendations: tuple[Recommendation, ...]
    education_card_codes: tuple[str, ...]
    unmapped_reason_codes: tuple[str, ...]
    needs_trusted_support_contact: bool


class GuidancePolicy:
    """Select only reviewed copy; unknown inputs get an explicit generic fallback."""

    _COMPLETENESS_REASON_CODES = frozenset({"analysis_partial", "analysis_unavailable"})

    def select(
        self,
        *,
        catalog: GuidanceCatalog,
        severity: Severity,
        completeness: GuidanceCompleteness,
        reason_codes: tuple[str, ...],
    ) -> GuidanceSelection:
        if not isinstance(reason_codes, tuple):
            raise TypeError("reason_codes must be a tuple")
        _require_codes(reason_codes, "reason_codes")
        if len(set(reason_codes)) != len(reason_codes):
            raise ValueError("reason_codes must be unique")
        classification = catalog.classification_for(severity)
        completeness_copy = catalog.completeness_for(completeness)
        mapped = {
            reason: recommendation
            for recommendation in catalog.recommendations
            for reason in recommendation.reason_codes
        }
        selected_codes = {mapped[reason].code for reason in reason_codes if reason in mapped}
        recognized_reasons = set(mapped) | self._COMPLETENESS_REASON_CODES
        unmapped = tuple(reason for reason in reason_codes if reason not in recognized_reasons)
        if completeness is GuidanceCompleteness.PARTIAL:
            selected_codes.add(catalog.partial_recommendation_code)
        elif completeness is GuidanceCompleteness.UNAVAILABLE:
            selected_codes.add(catalog.unavailable_recommendation_code)
        if unmapped:
            selected_codes.add(catalog.unsupported_reason_recommendation_code)
        if not selected_codes:
            selected_codes.add(catalog.default_recommendation_code)
        recommendations = tuple(
            item for item in catalog.recommendations if item.code in selected_codes
        )
        card_codes = tuple(
            dict.fromkeys(
                card_code
                for recommendation in recommendations
                for card_code in recommendation.education_card_codes
            )
        )
        return GuidanceSelection(
            risk_label=classification.risk_label,
            explanation=f"{classification.explanation} {completeness_copy.explanation}",
            recommendations=recommendations,
            education_card_codes=card_codes,
            unmapped_reason_codes=unmapped,
            needs_trusted_support_contact=any(
                item.uses_trusted_support_contact for item in recommendations
            ),
        )


def _require_code(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not _CODE.fullmatch(value):
        raise ValueError(f"{field_name} must use lower snake case")


def _require_codes(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    for item in value:
        _require_code(item, field_name)
    if len(set(value)) != len(value):
        raise ValueError(f"{field_name} must be unique")


def _require_plain_text(value: object, field_name: str, *, max_length: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip() or len(value) > max_length:
        raise ValueError(f"{field_name} must be non-empty, trimmed, and bounded")
    if any(character in value for character in "<>{}"):
        raise ValueError(f"{field_name} cannot contain raw markup")


def _require_utc(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC-aware")


def _require_unique_enum_values(
    values: object,
    *,
    expected: set[object],
    attribute: str,
    field_name: str,
) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    actual = {getattr(item, attribute, None) for item in values}
    if actual != expected or len(values) != len(expected):
        raise ValueError(f"{field_name} must cover every supported value exactly once")
