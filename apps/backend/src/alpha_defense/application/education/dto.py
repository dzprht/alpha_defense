"""Transport-neutral education and structured-guidance views."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from alpha_defense.domain.detection import AssessmentCompleteness
from alpha_defense.domain.shared import EntityId, Severity

_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


@dataclass(frozen=True, slots=True)
class AllowedActionView:
    code: str
    enabled: bool
    disabled_reason: str | None
    requires_confirmation: bool
    target_id: EntityId
    target_revision: int

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.code):
            raise ValueError("code must use lower snake case")
        if not isinstance(self.enabled, bool) or not isinstance(
            self.requires_confirmation,
            bool,
        ):
            raise TypeError("action flags must be booleans")
        if self.enabled and self.disabled_reason is not None:
            raise ValueError("enabled action cannot have a disabled reason")
        if not self.enabled and (
            not isinstance(self.disabled_reason, str)
            or not self.disabled_reason
            or self.disabled_reason != self.disabled_reason.strip()
        ):
            raise ValueError("disabled action requires a trimmed reason")
        if not isinstance(self.target_id, EntityId):
            raise TypeError("target_id must be an EntityId")
        if isinstance(self.target_revision, bool) or not isinstance(self.target_revision, int):
            raise TypeError("target_revision must be an integer")
        if self.target_revision < 0:
            raise ValueError("target_revision must be non-negative")


@dataclass(frozen=True, slots=True)
class RecommendationView:
    code: str
    title: str
    body: str


@dataclass(frozen=True, slots=True)
class EducationCardReferenceView:
    code: str
    version: str


@dataclass(frozen=True, slots=True)
class TrustedSupportContactView:
    code: str
    value: str


@dataclass(frozen=True, slots=True)
class GuidanceView:
    classification: Severity
    risk_label: str
    explanation: str
    completeness: AssessmentCompleteness
    recommendations: tuple[RecommendationView, ...]
    education_cards: tuple[EducationCardReferenceView, ...]
    allowed_actions: tuple[AllowedActionView, ...]
    support_message: str | None
    support_contact: TrustedSupportContactView | None
    unmapped_reason_codes: tuple[str, ...]
    locale: str
    requested_locale: str
    content_version: str


@dataclass(frozen=True, slots=True)
class EducationCardSummaryView:
    code: str
    version: str
    title: str
    summary: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class EducationCardPageView:
    items: tuple[EducationCardSummaryView, ...]
    next_cursor: str | None
    locale: str
    requested_locale: str
    locale_fallback: bool
    content_version: str


class CardFallbackReason(StrEnum):
    UNSUPPORTED_CODE = "unsupported_code"
    UNSUPPORTED_VERSION = "unsupported_version"


@dataclass(frozen=True, slots=True)
class EducationCardView:
    code: str
    version: str
    title: str
    summary: str
    body: str
    source_links: tuple[str, ...]
    reviewed_at: datetime
    locale: str
    requested_locale: str
    locale_fallback: bool
    requested_code: str
    requested_version: str | None
    fallback_reason: CardFallbackReason | None
    content_version: str
