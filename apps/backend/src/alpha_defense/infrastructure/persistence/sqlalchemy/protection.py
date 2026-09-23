"""SQLite warning inbox and lifecycle persistence."""

from __future__ import annotations

import json
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.shared import ServiceUnavailableError, StaleRevisionError
from alpha_defense.domain.protection import (
    Warning,
    WarningAction,
    WarningCompleteness,
    WarningResponse,
    WarningTargetKind,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode, Severity
from alpha_defense.infrastructure.persistence.sqlalchemy.mappers import as_utc
from alpha_defense.infrastructure.persistence.sqlalchemy.schema import warnings


class SqlAlchemyWarningRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, warning_id: EntityId) -> Warning | None:
        row = (
            self._session.execute(
                sa.select(warnings).where(warnings.c.warning_id == str(warning_id))
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _from_row(row)

    def get_by_assessment(self, assessment_id: EntityId) -> Warning | None:
        row = (
            self._session.execute(
                sa.select(warnings).where(warnings.c.assessment_id == str(assessment_id))
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _from_row(row)

    def list_dispatched(
        self, *, owner_id: EntityId, session_id: EntityId, namespace_id: EntityId
    ) -> tuple[Warning, ...]:
        rows = self._session.execute(
            sa.select(warnings)
            .where(
                warnings.c.owner_id == str(owner_id),
                warnings.c.session_id == str(session_id),
                warnings.c.namespace_id == str(namespace_id),
                warnings.c.dispatched_at.is_not(None),
            )
            .order_by(warnings.c.created_at, warnings.c.warning_id)
        ).mappings()
        return tuple(_from_row(row) for row in rows)

    def add(self, warning: Warning) -> None:
        try:
            self._session.execute(sa.insert(warnings).values(_values(warning)))
        except SQLAlchemyError as exc:
            raise ServiceUnavailableError("Local warning persistence failed") from exc

    def save(self, warning: Warning, *, expected_revision: int) -> None:
        current = self.get(warning.warning_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Warning revision is stale")
        if warning.revision != expected_revision + 1:
            raise StaleRevisionError("Warning revision must advance by one")
        current.assert_successor(warning)
        result = self._session.execute(
            sa.update(warnings)
            .where(
                warnings.c.warning_id == str(warning.warning_id),
                warnings.c.revision == expected_revision,
            )
            .values(
                dispatched_at=warning.dispatched_at,
                presented_at=warning.presented_at,
                responded_at=warning.responded_at,
                response=None if warning.response is None else warning.response.value,
                selected_action_code=warning.selected_action_code,
                revision=warning.revision,
            )
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            raise StaleRevisionError("Warning revision is stale")


def _values(warning: Warning) -> dict[str, Any]:
    return {
        "warning_id": str(warning.warning_id),
        "assessment_id": str(warning.assessment_id),
        "owner_id": str(warning.owner_id),
        "session_id": str(warning.session_id),
        "namespace_id": str(warning.namespace_id),
        "target_kind": warning.target_kind.value,
        "target_id": str(warning.target_id),
        "context_version": warning.context_version,
        "severity": warning.severity.value,
        "completeness": warning.completeness.value,
        "risk_label": warning.risk_label,
        "explanation": warning.explanation,
        "content_version": warning.content_version,
        "allowed_actions_json": json.dumps(
            [
                {
                    "code": action.code,
                    "enabled": action.enabled,
                    "disabled_reason": action.disabled_reason,
                    "requires_confirmation": action.requires_confirmation,
                    "target_id": str(action.target_id),
                    "target_revision": action.target_revision,
                }
                for action in warning.allowed_actions
            ],
            ensure_ascii=False,
            sort_keys=True,
        ),
        "created_at": warning.created_at,
        "execution_mode": warning.execution_mode.value,
        "dispatched_at": warning.dispatched_at,
        "presented_at": warning.presented_at,
        "responded_at": warning.responded_at,
        "response": None if warning.response is None else warning.response.value,
        "selected_action_code": warning.selected_action_code,
        "revision": warning.revision,
    }


def _from_row(row: RowMapping) -> Warning:
    actions = json.loads(row["allowed_actions_json"])
    return Warning(
        warning_id=EntityId.from_string(row["warning_id"]),
        assessment_id=EntityId.from_string(row["assessment_id"]),
        owner_id=EntityId.from_string(row["owner_id"]),
        session_id=EntityId.from_string(row["session_id"]),
        namespace_id=EntityId.from_string(row["namespace_id"]),
        target_kind=WarningTargetKind(row["target_kind"]),
        target_id=EntityId.from_string(row["target_id"]),
        context_version=row["context_version"],
        severity=Severity(row["severity"]),
        completeness=WarningCompleteness(row["completeness"]),
        risk_label=row["risk_label"],
        explanation=row["explanation"],
        content_version=row["content_version"],
        allowed_actions=tuple(
            WarningAction(
                code=action["code"],
                enabled=action["enabled"],
                disabled_reason=action["disabled_reason"],
                requires_confirmation=action["requires_confirmation"],
                target_id=EntityId.from_string(action["target_id"]),
                target_revision=action["target_revision"],
            )
            for action in actions
        ),
        created_at=as_utc(row["created_at"]),
        execution_mode=ExecutionMode(row["execution_mode"]),
        dispatched_at=None if row["dispatched_at"] is None else as_utc(row["dispatched_at"]),
        presented_at=None if row["presented_at"] is None else as_utc(row["presented_at"]),
        responded_at=None if row["responded_at"] is None else as_utc(row["responded_at"]),
        response=None if row["response"] is None else WarningResponse(row["response"]),
        selected_action_code=row["selected_action_code"],
        revision=row["revision"],
    )
