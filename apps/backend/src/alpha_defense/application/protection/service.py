"""Store an in-app warning without treating a UI response as execution."""

from __future__ import annotations

from datetime import datetime

from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    EventEnvelope,
    IdGenerator,
    WarningUnitOfWorkFactory,
    WarningUnitOfWorkPort,
)
from alpha_defense.application.protection.dto import WarningDraft
from alpha_defense.application.shared import ActorContext, ResourceNotFoundError, ValidationError
from alpha_defense.domain.protection import Warning, WarningCompleteness, WarningResponse
from alpha_defense.domain.shared import EntityId, Severity


class WarningService:
    """Lifecycle boundary; delivery, render, and response are separate facts."""

    def __init__(
        self,
        *,
        unit_of_work: WarningUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_generator = id_generator

    def create(
        self,
        *,
        actor: ActorContext,
        draft: WarningDraft,
    ) -> Warning | None:
        with self._unit_of_work() as uow:
            warning = self.create_in_unit_of_work(uow=uow, actor=actor, draft=draft)
            uow.commit()
        return warning

    def create_in_unit_of_work(
        self,
        *,
        uow: WarningUnitOfWorkPort,
        actor: ActorContext,
        draft: WarningDraft,
    ) -> Warning | None:
        existing = uow.warnings.get_by_assessment(draft.assessment_id)
        if existing is not None:
            if not _owned(existing, actor):
                raise ResourceNotFoundError("Предупреждение не найдено.")
            return existing
        if draft.severity is Severity.LOW and draft.completeness is WarningCompleteness.COMPLETE:
            return None
        now = self._clock.now_utc()
        warning = Warning(
            warning_id=self._id_generator.new_id(),
            assessment_id=draft.assessment_id,
            owner_id=actor.user_id,
            session_id=actor.session_id,
            namespace_id=actor.namespace_id,
            target_kind=draft.target_kind,
            target_id=draft.target_id,
            context_version=draft.context_version,
            severity=draft.severity,
            completeness=draft.completeness,
            risk_label=draft.risk_label,
            explanation=draft.explanation,
            content_version=draft.content_version,
            allowed_actions=draft.allowed_actions,
            created_at=now,
            execution_mode=actor.execution_mode,
        )
        uow.warnings.add(warning)
        self._audit(uow, actor, warning, "warning.created", now)
        return warning

    def get(self, *, actor: ActorContext, warning_id: EntityId) -> Warning:
        with self._unit_of_work() as uow:
            return _get_owned(uow, actor, warning_id)

    def list_dispatched(self, *, actor: ActorContext) -> tuple[Warning, ...]:
        with self._unit_of_work() as uow:
            return uow.warnings.list_dispatched(
                owner_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
            )

    def dispatch(self, *, actor: ActorContext, warning_id: EntityId) -> Warning:
        return self._change(actor=actor, warning_id=warning_id, kind="dispatch")

    def present(self, *, actor: ActorContext, warning_id: EntityId) -> Warning:
        return self._change(actor=actor, warning_id=warning_id, kind="present")

    def respond(
        self,
        *,
        actor: ActorContext,
        warning_id: EntityId,
        response: WarningResponse,
        selected_action_code: str | None = None,
    ) -> Warning:
        return self._change(
            actor=actor,
            warning_id=warning_id,
            kind="respond",
            response=response,
            selected_action_code=selected_action_code,
        )

    def _change(
        self,
        *,
        actor: ActorContext,
        warning_id: EntityId,
        kind: str,
        response: WarningResponse | None = None,
        selected_action_code: str | None = None,
    ) -> Warning:
        with self._unit_of_work() as uow:
            current = _get_owned(uow, actor, warning_id)
            now = self._clock.now_utc()
            try:
                if kind == "dispatch":
                    updated = current.dispatch(now)
                elif kind == "present":
                    updated = current.present(now)
                elif response is not None:
                    updated = current.respond(
                        response=response, at=now, selected_action_code=selected_action_code
                    )
                else:
                    raise ValueError("unknown warning transition")
            except ValueError as exc:
                raise ValidationError("Недопустимое состояние предупреждения.") from exc
            if updated != current:
                uow.warnings.save(updated, expected_revision=current.revision)
                self._audit(uow, actor, updated, f"warning.{kind}", now)
            uow.commit()
        return updated

    def _audit(
        self,
        uow: WarningUnitOfWorkPort,
        actor: ActorContext,
        warning: Warning,
        event_type: str,
        at: datetime,
    ) -> None:
        uow.audit.append(
            AuditRecord(
                event=EventEnvelope(
                    event_id=self._id_generator.new_id(),
                    event_type=event_type,
                    aggregate_id=warning.warning_id,
                    aggregate_revision=warning.revision,
                    occurred_at=at,
                    correlation_id=warning.assessment_id,
                    execution_mode=actor.execution_mode,
                    payload={
                        "assessment_id": str(warning.assessment_id),
                        "context_version": warning.context_version,
                        "response": None if warning.response is None else warning.response.value,
                        "selected_action_code": warning.selected_action_code,
                    },
                ),
                actor_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                recorded_at=at,
            )
        )


def _owned(warning: Warning, actor: ActorContext) -> bool:
    return (
        warning.owner_id == actor.user_id
        and warning.session_id == actor.session_id
        and warning.namespace_id == actor.namespace_id
        and warning.execution_mode is actor.execution_mode
    )


def _get_owned(uow: WarningUnitOfWorkPort, actor: ActorContext, warning_id: EntityId) -> Warning:
    warning = uow.warnings.get(warning_id)
    if warning is None or not _owned(warning, actor):
        raise ResourceNotFoundError("Предупреждение не найдено.")
    return warning
