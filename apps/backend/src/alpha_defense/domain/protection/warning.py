"""A warning is a record of risk communication, not a transfer decision."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from alpha_defense.domain.shared import EntityId, ExecutionMode, Severity

_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class WarningResponse(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    ACTION_SELECTED = "action_selected"


class WarningCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class WarningTargetKind(StrEnum):
    OBSERVATION = "observation"
    TRANSFER = "transfer"


@dataclass(frozen=True, slots=True)
class WarningAction:
    code: str
    enabled: bool
    disabled_reason: str | None
    requires_confirmation: bool
    target_id: EntityId
    target_revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not _CODE.fullmatch(self.code):
            raise ValueError("action code must use lower snake case")
        if not isinstance(self.enabled, bool) or not isinstance(self.requires_confirmation, bool):
            raise TypeError("action flags must be booleans")
        if self.enabled and self.disabled_reason is not None:
            raise ValueError("enabled action cannot have a disabled reason")
        if not self.enabled and (
            not isinstance(self.disabled_reason, str)
            or not self.disabled_reason
            or self.disabled_reason != self.disabled_reason.strip()
        ):
            raise ValueError("disabled action requires a reason")
        if not isinstance(self.target_id, EntityId) or type(self.target_revision) is not int:
            raise TypeError("action target must have an ID and integer revision")
        if self.target_revision < 0:
            raise ValueError("action target revision must be non-negative")


@dataclass(frozen=True, slots=True)
class Warning:
    warning_id: EntityId
    assessment_id: EntityId
    owner_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    target_kind: WarningTargetKind
    target_id: EntityId
    context_version: int
    severity: Severity
    completeness: WarningCompleteness
    risk_label: str
    explanation: str
    content_version: str
    allowed_actions: tuple[WarningAction, ...]
    created_at: datetime
    execution_mode: ExecutionMode
    dispatched_at: datetime | None = None
    presented_at: datetime | None = None
    responded_at: datetime | None = None
    response: WarningResponse | None = None
    selected_action_code: str | None = None
    revision: int = 0

    def __post_init__(self) -> None:
        for name in (
            "warning_id",
            "assessment_id",
            "owner_id",
            "session_id",
            "namespace_id",
            "target_id",
        ):
            if not isinstance(getattr(self, name), EntityId):
                raise TypeError(f"{name} must be an EntityId")
        if not isinstance(self.target_kind, WarningTargetKind):
            raise TypeError("target_kind must be a WarningTargetKind")
        if not isinstance(self.severity, Severity) or not isinstance(
            self.completeness, WarningCompleteness
        ):
            raise TypeError("risk classification is invalid")
        if (
            self.completeness is WarningCompleteness.UNAVAILABLE
            and self.severity is not Severity.UNKNOWN
        ):
            raise ValueError("unavailable warning must have unknown severity")
        if (
            self.completeness is not WarningCompleteness.UNAVAILABLE
            and self.severity is Severity.UNKNOWN
        ):
            raise ValueError("known analysis requires known severity")
        if type(self.context_version) is not int or self.context_version < 1:
            raise ValueError("context_version must be positive")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("revision must be non-negative")
        for name in ("risk_label", "explanation", "content_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{name} must be non-empty and trimmed")
        if (
            len(self.risk_label) > 160
            or len(self.explanation) > 4000
            or len(self.content_version) > 128
        ):
            raise ValueError("warning copy or version is too long")
        if not isinstance(self.allowed_actions, tuple) or any(
            not isinstance(action, WarningAction) for action in self.allowed_actions
        ):
            raise TypeError("allowed_actions must contain WarningAction values")
        if len({action.code for action in self.allowed_actions}) != len(self.allowed_actions):
            raise ValueError("allowed action codes must be unique")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        for name in ("created_at", "dispatched_at", "presented_at", "responded_at"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() != UTC.utcoffset(value)
            ):
                raise ValueError(f"{name} must be UTC-aware")
        if self.created_at is None:
            raise ValueError("created_at is required")
        if self.dispatched_at is not None and self.dispatched_at < self.created_at:
            raise ValueError("dispatch cannot precede creation")
        if self.presented_at is not None and (
            self.dispatched_at is None or self.presented_at < self.dispatched_at
        ):
            raise ValueError("presentation requires dispatch")
        if self.responded_at is not None and (
            self.presented_at is None or self.responded_at < self.presented_at
        ):
            raise ValueError("response requires presentation")
        if (self.response is None) != (self.responded_at is None):
            raise ValueError("response and responded_at must appear together")
        if self.response is not None and not isinstance(self.response, WarningResponse):
            raise TypeError("response must be a WarningResponse")
        if self.response is WarningResponse.ACTION_SELECTED:
            if self.selected_action_code not in {
                action.code for action in self.allowed_actions if action.enabled
            }:
                raise ValueError("selected action must be server-enabled")
        elif self.selected_action_code is not None:
            raise ValueError("selected action requires action_selected response")

    def dispatch(self, at: datetime) -> Warning:
        if self.dispatched_at is not None:
            return self
        return replace(self, dispatched_at=at, revision=self.revision + 1)

    def present(self, at: datetime) -> Warning:
        if self.dispatched_at is None:
            raise ValueError("warning must be dispatched before presentation")
        if self.presented_at is not None:
            return self
        return replace(self, presented_at=at, revision=self.revision + 1)

    def respond(
        self,
        *,
        response: WarningResponse,
        at: datetime,
        selected_action_code: str | None = None,
    ) -> Warning:
        if self.presented_at is None:
            raise ValueError("warning must be presented before response")
        if self.responded_at is not None:
            if self.response is response and self.selected_action_code == selected_action_code:
                return self
            raise ValueError("warning already has a different response")
        return replace(
            self,
            response=response,
            selected_action_code=selected_action_code,
            responded_at=at,
            revision=self.revision + 1,
        )

    def assert_successor(self, updated: Warning) -> None:
        """Protect immutable risk/actions and the one-fact-at-a-time lifecycle."""

        immutable = (
            "warning_id",
            "assessment_id",
            "owner_id",
            "session_id",
            "namespace_id",
            "target_kind",
            "target_id",
            "context_version",
            "severity",
            "completeness",
            "risk_label",
            "explanation",
            "content_version",
            "allowed_actions",
            "created_at",
            "execution_mode",
        )
        if any(getattr(self, name) != getattr(updated, name) for name in immutable):
            raise ValueError("immutable warning data cannot be changed")
        if updated.revision != self.revision + 1:
            raise ValueError("warning revision must advance by one")
        if self.dispatched_at is None:
            valid = updated.dispatched_at is not None and updated.presented_at is None
        elif self.presented_at is None:
            valid = (
                updated.dispatched_at == self.dispatched_at
                and updated.presented_at is not None
                and updated.responded_at is None
            )
        elif self.responded_at is None:
            valid = (
                updated.dispatched_at == self.dispatched_at
                and updated.presented_at == self.presented_at
                and updated.responded_at is not None
            )
        else:
            valid = False
        if not valid:
            raise ValueError("warning lifecycle must advance one fact at a time")
