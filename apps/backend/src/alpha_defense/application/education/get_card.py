"""Read one immutable education card with explicit fallback metadata."""

from __future__ import annotations

import re

from alpha_defense.application.education.dto import CardFallbackReason, EducationCardView
from alpha_defense.application.ports import ContentCatalogPort
from alpha_defense.application.shared import ValidationError

_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_FALLBACK_CARD_CODE = "general_safety"


class GetCard:
    def __init__(self, catalog: ContentCatalogPort) -> None:
        self._catalog = catalog

    def execute(
        self,
        *,
        code: str,
        locale: str = "ru-RU",
        version: str | None = None,
    ) -> EducationCardView:
        _validate_code(code)
        _validate_locale(locale)
        _validate_version(version)
        snapshot = self._catalog.load_education(locale)
        card = self._catalog.get_education_card(code, locale, version)
        fallback_reason: CardFallbackReason | None = None
        if card is None:
            known_code = any(item.code == code for item in snapshot.cards)
            fallback_reason = (
                CardFallbackReason.UNSUPPORTED_VERSION
                if known_code
                else CardFallbackReason.UNSUPPORTED_CODE
            )
            card = self._catalog.get_education_card(_FALLBACK_CARD_CODE, locale)
            if card is None:
                raise RuntimeError("mandatory general safety card was not loaded")
        return EducationCardView(
            code=card.code,
            version=card.version,
            title=card.title,
            summary=card.summary,
            body=card.body,
            source_links=card.source_links,
            reviewed_at=card.reviewed_at,
            locale=card.locale,
            requested_locale=locale,
            locale_fallback=card.locale != locale,
            requested_code=code,
            requested_version=version,
            fallback_reason=fallback_reason,
            content_version=snapshot.content_sha256,
        )


def _validate_code(code: str) -> None:
    if not isinstance(code, str) or not _CODE.fullmatch(code):
        raise ValidationError("Код карточки имеет неверный формат.")


def _validate_locale(locale: str) -> None:
    if not isinstance(locale, str) or not _LOCALE.fullmatch(locale):
        raise ValidationError("Локаль должна иметь формат language-REGION.")


def _validate_version(version: str | None) -> None:
    if version is not None and (not isinstance(version, str) or not _SEMVER.fullmatch(version)):
        raise ValidationError("Версия карточки должна иметь формат x.y.z.")
