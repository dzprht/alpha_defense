"""Transport-neutral input for a reviewed warning snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_defense.domain.protection import (
    WarningAction,
    WarningCompleteness,
    WarningTargetKind,
)
from alpha_defense.domain.shared import EntityId, Severity


@dataclass(frozen=True, slots=True)
class WarningDraft:
    assessment_id: EntityId
    target_kind: WarningTargetKind
    target_id: EntityId
    context_version: int
    severity: Severity
    completeness: WarningCompleteness
    risk_label: str
    explanation: str
    content_version: str
    allowed_actions: tuple[WarningAction, ...]
