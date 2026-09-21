"""List immutable education cards with opaque cursor pagination."""

# ruff: noqa: RUF001

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import TypedDict

from alpha_defense.application.education.dto import (
    EducationCardPageView,
    EducationCardSummaryView,
)
from alpha_defense.application.ports import ContentCatalogPort
from alpha_defense.application.shared import PageRequest, ValidationError
from alpha_defense.domain.education import EducationCard

_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


class _CursorPayload(TypedDict):
    content_version: str
    offset: int


class ListCards:
    def __init__(self, catalog: ContentCatalogPort) -> None:
        self._catalog = catalog

    def execute(
        self,
        *,
        page: PageRequest,
        locale: str = "ru-RU",
    ) -> EducationCardPageView:
        _validate_locale(locale)
        snapshot = self._catalog.load_education(locale)
        offset = _decode_cursor(page.cursor, snapshot.content_sha256)
        if offset > len(snapshot.cards):
            raise ValidationError("Курсор учебного каталога устарел или повреждён.")
        selected = snapshot.cards[offset : offset + page.limit]
        next_offset = offset + len(selected)
        next_cursor = (
            _encode_cursor(snapshot.content_sha256, next_offset)
            if next_offset < len(snapshot.cards)
            else None
        )
        return EducationCardPageView(
            items=tuple(_summary(card) for card in selected),
            next_cursor=next_cursor,
            locale=snapshot.locale,
            requested_locale=locale,
            locale_fallback=snapshot.locale != locale,
            content_version=snapshot.content_sha256,
        )


def _summary(card: EducationCard) -> EducationCardSummaryView:
    return EducationCardSummaryView(
        code=card.code,
        version=card.version,
        title=card.title,
        summary=card.summary,
        reviewed_at=card.reviewed_at,
    )


def _encode_cursor(content_version: str, offset: int) -> str:
    payload: _CursorPayload = {"content_version": content_version, "offset": offset}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str | None, content_version: str) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value: object = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if not isinstance(value, dict) or set(value) != {"content_version", "offset"}:
            raise ValueError
        version = value["content_version"]
        offset = value["offset"]
        if version != content_version or isinstance(offset, bool) or not isinstance(offset, int):
            raise ValueError
        if offset < 0:
            raise ValueError
        return offset
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        raise ValidationError("Курсор учебного каталога устарел или повреждён.") from None


def _validate_locale(locale: str) -> None:
    if not isinstance(locale, str) or not _LOCALE.fullmatch(locale):
        raise ValidationError("Локаль должна иметь формат language-REGION.")
