"""Acceptance tests for structured guidance and education use cases."""

# ruff: noqa: RUF001

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from tests.catalog_helpers import install_valid_catalog

from alpha_defense.application.education import (
    AllowedActionView,
    CardFallbackReason,
    GetCard,
    GetGuidance,
    ListCards,
)
from alpha_defense.application.shared import (
    ActorContext,
    ActorRole,
    PageRequest,
    ResourceNotFoundError,
    ValidationError,
)
from alpha_defense.domain.detection import (
    AssessmentCompleteness,
    AssessmentTargetKind,
    RiskAssessment,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode, Provenance, Severity
from alpha_defense.infrastructure.content import LocalCatalogLoader

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _id(value: int) -> EntityId:
    return EntityId(UUID(int=value))


DEFAULT_OWNER_ID = _id(1)


def _actor(owner_id: EntityId = DEFAULT_OWNER_ID) -> ActorContext:
    return ActorContext(
        user_id=owner_id,
        session_id=_id(2),
        namespace_id=_id(3),
        roles=frozenset({ActorRole.DEMO_USER}),
        consent_revision=0,
        execution_mode=ExecutionMode.MOCK,
    )


def _assessment(
    *,
    completeness: AssessmentCompleteness = AssessmentCompleteness.COMPLETE,
    reason_codes: tuple[str, ...] = ("credential_request",),
) -> RiskAssessment:
    unavailable = completeness is AssessmentCompleteness.UNAVAILABLE
    return RiskAssessment(
        assessment_id=_id(4),
        owner_id=_id(1),
        session_id=_id(2),
        namespace_id=_id(3),
        target_kind=AssessmentTargetKind.OBSERVATION,
        target_id=_id(5),
        severity=Severity.UNKNOWN if unavailable else Severity.HIGH,
        score=None if unavailable else 70,
        score_kind="heuristic",
        completeness=completeness,
        signals=(),
        applied_modifiers=(),
        reason_codes=reason_codes,
        analyzer_results=(),
        policy_version="demo-risk-v1",
        analysis_plan_version="observation-v1",
        assessed_at=NOW,
        context_version=1,
        provenance=Provenance(ExecutionMode.MOCK, "fixture", "1", "1"),
        has_mock_evidence=True,
    )


@pytest.fixture
def catalog(tmp_path: Path) -> LocalCatalogLoader:
    install_valid_catalog(tmp_path)
    return LocalCatalogLoader(
        schema_root=tmp_path / "schemas",
        content_root=tmp_path / "content",
        fixture_root=tmp_path / "fixtures",
        policy_version="demo-risk-v1",
    )


def test_guidance_uses_reviewed_copy_server_actions_and_trusted_contact(
    catalog: LocalCatalogLoader,
) -> None:
    action = AllowedActionView(
        code="report_incident",
        enabled=True,
        disabled_reason=None,
        requires_confirmation=True,
        target_id=_id(5),
        target_revision=1,
    )

    guidance = GetGuidance(catalog).execute(
        actor=_actor(),
        assessment=_assessment(),
        allowed_actions=(action,),
        locale="ru-RU",
    )

    assert guidance.risk_label == "Высокий риск"
    assert [item.code for item in guidance.recommendations] == ["protect_credentials"]
    assert guidance.allowed_actions == (action,)
    assert guidance.support_contact is not None
    assert guidance.support_contact.value == "900"
    assert guidance.education_cards[0].code == "credential_requests"


def test_guidance_marks_unknown_reason_and_partial_analysis_without_inventing_detail(
    catalog: LocalCatalogLoader,
) -> None:
    guidance = GetGuidance(catalog).execute(
        actor=_actor(),
        assessment=_assessment(
            completeness=AssessmentCompleteness.PARTIAL,
            reason_codes=("future_signal", "analysis_partial"),
        ),
        allowed_actions=(),
        locale="en-US",
    )

    assert guidance.locale == "ru-RU"
    assert guidance.requested_locale == "en-US"
    assert guidance.unmapped_reason_codes == ("future_signal",)
    assert {item.code for item in guidance.recommendations} == {
        "unsupported_reason",
        "repeat_partial_check",
    }
    assert guidance.support_contact is None


def test_guidance_uses_official_channel_fallback_when_trusted_contact_is_absent(
    catalog: LocalCatalogLoader,
) -> None:
    class CatalogWithoutContact(LocalCatalogLoader):
        def trusted_support_contact(self) -> None:
            return None

    unavailable_contact_catalog = CatalogWithoutContact(
        schema_root=catalog._schema_root,
        content_root=catalog._content_root,
        fixture_root=catalog._fixture_root,
        policy_version=catalog._policy_version,
    )

    guidance = GetGuidance(unavailable_contact_catalog).execute(
        actor=_actor(),
        assessment=_assessment(),
        allowed_actions=(),
    )

    assert guidance.support_contact is None
    assert guidance.support_message is not None
    assert "900" not in guidance.support_message
    assert "официальный сайт или приложение" in guidance.support_message


def test_guidance_hides_assessment_from_another_owner(catalog: LocalCatalogLoader) -> None:
    with pytest.raises(ResourceNotFoundError, match="Оценка риска не найдена"):
        GetGuidance(catalog).execute(
            actor=_actor(_id(99)),
            assessment=_assessment(),
            allowed_actions=(),
        )


def test_cards_paginate_and_fall_back_for_locale_code_and_version(
    catalog: LocalCatalogLoader,
) -> None:
    service = ListCards(catalog)
    first = service.execute(page=PageRequest(limit=2), locale="en-US")
    second = service.execute(
        page=PageRequest(limit=100, cursor=first.next_cursor),
        locale="en-US",
    )
    unknown = GetCard(catalog).execute(code="future_card", locale="en-US")
    old = GetCard(catalog).execute(
        code="general_safety",
        locale="ru-RU",
        version="9.9.9",
    )

    assert len(first.items) == 2
    assert len(second.items) == 5
    assert first.locale_fallback
    assert unknown.code == "general_safety"
    assert unknown.fallback_reason is CardFallbackReason.UNSUPPORTED_CODE
    assert old.fallback_reason is CardFallbackReason.UNSUPPORTED_VERSION


def test_cards_reject_malformed_or_stale_cursor(catalog: LocalCatalogLoader) -> None:
    with pytest.raises(ValidationError, match="Курсор"):
        ListCards(catalog).execute(page=PageRequest(cursor="not-base64"))
