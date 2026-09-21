"""Public education card schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from alpha_defense.application.education import (
    EducationCardPageView,
    EducationCardSummaryView,
    EducationCardView,
)


class EducationCardSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    version: str = Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=300)
    reviewed_at: datetime

    @classmethod
    def from_view(cls, view: EducationCardSummaryView) -> EducationCardSummaryResponse:
        return cls(
            code=view.code,
            version=view.version,
            title=view.title,
            summary=view.summary,
            reviewed_at=view.reviewed_at,
        )


class EducationCardPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[EducationCardSummaryResponse, ...]
    next_cursor: str | None
    locale: str = Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")
    requested_locale: str = Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")
    locale_fallback: bool
    content_version: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_view(cls, view: EducationCardPageView) -> EducationCardPageResponse:
        return cls(
            items=tuple(EducationCardSummaryResponse.from_view(item) for item in view.items),
            next_cursor=view.next_cursor,
            locale=view.locale,
            requested_locale=view.requested_locale,
            locale_fallback=view.locale_fallback,
            content_version=view.content_version,
        )


class EducationCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    version: str = Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=10_000)
    source_links: tuple[str, ...]
    reviewed_at: datetime
    locale: str = Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")
    requested_locale: str = Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")
    locale_fallback: bool
    requested_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    requested_version: str | None
    fallback_reason: Literal["unsupported_code", "unsupported_version"] | None
    content_version: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_view(cls, view: EducationCardView) -> EducationCardResponse:
        return cls(
            code=view.code,
            version=view.version,
            title=view.title,
            summary=view.summary,
            body=view.body,
            source_links=view.source_links,
            reviewed_at=view.reviewed_at,
            locale=view.locale,
            requested_locale=view.requested_locale,
            locale_fallback=view.locale_fallback,
            requested_code=view.requested_code,
            requested_version=view.requested_version,
            fallback_reason=view.fallback_reason,
            content_version=view.content_version,
        )
