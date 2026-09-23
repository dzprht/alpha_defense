"""Coordinate assessment, reviewed guidance, and protection boundaries."""

from __future__ import annotations

from alpha_defense.application.education import AllowedActionView, GetGuidance
from alpha_defense.application.ports import WarningUnitOfWorkPort
from alpha_defense.application.protection import WarningDraft, WarningService
from alpha_defense.application.shared import ActorContext, ResourceNotFoundError
from alpha_defense.domain.detection import RiskAssessment
from alpha_defense.domain.protection import (
    Warning,
    WarningAction,
    WarningCompleteness,
    WarningTargetKind,
)


class PublishWarning:
    """Build only from a server assessment and reviewed content."""

    def __init__(self, *, guidance: GetGuidance, warnings: WarningService) -> None:
        self._guidance = guidance
        self._warnings = warnings

    def execute(
        self,
        *,
        actor: ActorContext,
        assessment: RiskAssessment,
        allowed_actions: tuple[AllowedActionView, ...],
    ) -> Warning | None:
        draft = self._draft(actor, assessment, allowed_actions)
        return self._warnings.create(actor=actor, draft=draft)

    def execute_in_unit_of_work(
        self,
        *,
        uow: WarningUnitOfWorkPort,
        actor: ActorContext,
        assessment: RiskAssessment,
        allowed_actions: tuple[AllowedActionView, ...],
    ) -> Warning | None:
        draft = self._draft(actor, assessment, allowed_actions)
        return self._warnings.create_in_unit_of_work(uow=uow, actor=actor, draft=draft)

    def _draft(
        self,
        actor: ActorContext,
        assessment: RiskAssessment,
        allowed_actions: tuple[AllowedActionView, ...],
    ) -> WarningDraft:
        if assessment.provenance.execution_mode is not actor.execution_mode:
            raise ResourceNotFoundError("Оценка риска не найдена.")
        guidance = self._guidance.execute(
            actor=actor, assessment=assessment, allowed_actions=allowed_actions
        )
        return WarningDraft(
            assessment_id=assessment.assessment_id,
            target_kind=WarningTargetKind(assessment.target_kind.value),
            target_id=assessment.target_id,
            context_version=assessment.context_version,
            severity=assessment.severity,
            completeness=WarningCompleteness(assessment.completeness.value),
            risk_label=guidance.risk_label,
            explanation=guidance.explanation,
            content_version=guidance.content_version,
            allowed_actions=tuple(
                WarningAction(
                    code=action.code,
                    enabled=action.enabled,
                    disabled_reason=action.disabled_reason,
                    requires_confirmation=action.requires_confirmation,
                    target_id=action.target_id,
                    target_revision=action.target_revision,
                )
                for action in guidance.allowed_actions
            ),
        )
