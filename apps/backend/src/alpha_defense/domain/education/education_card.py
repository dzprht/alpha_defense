"""Published, immutable, and non-executable education cards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class EducationCard:
    code: str
    locale: str
    version: str
    title: str
    summary: str
    body: str
    source_links: tuple[str, ...]
    reviewed_at: datetime
    status: str
    content_sha256: str

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.code):
            raise ValueError("code must use lower snake case")
        if not _LOCALE.fullmatch(self.locale):
            raise ValueError("locale must use language-REGION format")
        if not _SEMVER.fullmatch(self.version):
            raise ValueError("version must be semantic x.y.z")
        _require_text(self.title, "title", max_length=120)
        _require_text(self.summary, "summary", max_length=300)
        _require_text(self.body, "body", max_length=10_000)
        if any(character in self.title + self.summary for character in "<>{}"):
            raise ValueError("title and summary cannot contain raw markup")
        if any(character in self.body for character in "<>{}") or re.search(
            r"(?:^|\n)\s*(?:import|export)\s",
            self.body,
        ):
            raise ValueError("body cannot contain raw HTML or MDX")
        if not isinstance(self.source_links, tuple) or any(
            not isinstance(item, str) or not item.startswith("https://") or len(item) > 2048
            for item in self.source_links
        ):
            raise ValueError("source_links must contain bounded HTTPS URLs")
        if len(set(self.source_links)) != len(self.source_links):
            raise ValueError("source_links must be unique")
        if not isinstance(self.reviewed_at, datetime):
            raise TypeError("reviewed_at must be a datetime")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() != UTC.utcoffset(
            self.reviewed_at
        ):
            raise ValueError("reviewed_at must be UTC-aware")
        if self.status != "published":
            raise ValueError("only published cards can enter the runtime catalog")
        if not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a lowercase SHA-256 digest")


def _require_text(value: object, field_name: str, *, max_length: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip() or len(value) > max_length:
        raise ValueError(f"{field_name} must be non-empty, trimmed, and bounded")
