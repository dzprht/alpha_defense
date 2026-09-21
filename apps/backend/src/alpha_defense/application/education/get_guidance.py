"""Build structured guidance from a completed risk assessment."""

from __future__ import annotations

import re

from alpha_defense.application.education.dto import (
    AllowedActionView,
    EducationCardReferenceView,
    GuidanceView,
    RecommendationView,
    TrustedSupportContactView,
)
from alpha_defense.application.ports import ContentCatalogPort
from alpha_defense.application.shared import ActorContext, ResourceNotFoundError, ValidationError
from alpha_defense.domain.detection import RiskAssessment
from alpha_defense.domain.education import GuidanceCompleteness, GuidancePolicy

_LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


class GetGuidance:
    """Select reviewed copy without deriving execution capabilities."""

    def __init__(self, catalog: ContentCatalogPort) -> None:
        self._catalog = catalog
        self._policy = GuidancePolicy()

    def execute(
        self,
        *,
        actor: ActorContext,
        assessment: RiskAssessment,
        allowed_actions: tuple[AllowedActionView, ...],
        locale: str = "ru-RU",
    ) -> GuidanceView:
        _validate_locale(locale)
        if (
            assessment.owner_id != actor.user_id
            or assessment.session_id != actor.session_id
            or assessment.namespace_id != actor.namespace_id
        ):
            raise ResourceNotFoundError("Оценка риска не найдена.")
        if not isinstance(allowed_actions, tuple) or any(
            not isinstance(action, AllowedActionView) for action in allowed_actions
        ):
            raise TypeError("allowed_actions must contain AllowedActionView values")
        if len({action.code for action in allowed_actions}) != len(allowed_actions):
            raise ValueError("allowed action codes must be unique")

        catalog = self._catalog.load_guidance(locale)
        selection = self._policy.select(
            catalog=catalog,
            severity=assessment.severity,
            completeness=GuidanceCompleteness(assessment.completeness.value),
            reason_codes=assessment.reason_codes,
        )
        cards = self._catalog.load_education(locale)
        versions = {card.code: card.version for card in cards.cards}
        support_message: str | None = None
        support_contact: TrustedSupportContactView | None = None
        if selection.needs_trusted_support_contact:
            trusted = self._catalog.trusted_support_contact()
            if trusted is None:
                support_message = catalog.support_without_contact
            else:
                support_message = catalog.support_with_contact
                support_contact = TrustedSupportContactView(
                    code=trusted.code,
                    value=trusted.value,
                )
        return GuidanceView(
            classification=assessment.severity,
            risk_label=selection.risk_label,
            explanation=selection.explanation,
            completeness=assessment.completeness,
            recommendations=tuple(
                RecommendationView(
                    code=item.code,
                    title=item.title,
                    body=item.body,
                )
                for item in selection.recommendations
            ),
            education_cards=tuple(
                EducationCardReferenceView(code=code, version=versions[code])
                for code in selection.education_card_codes
            ),
            allowed_actions=allowed_actions,
            support_message=support_message,
            support_contact=support_contact,
            unmapped_reason_codes=selection.unmapped_reason_codes,
            locale=cards.locale,
            requested_locale=locale,
            content_version=catalog.catalog_version,
        )


def _validate_locale(locale: str) -> None:
    if not isinstance(locale, str) or not _LOCALE.fullmatch(locale):
        raise ValidationError("Локаль должна иметь формат language-REGION.")
