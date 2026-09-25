"""Safe public warning snapshot and presentation acknowledgement."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from alpha_defense.application.protection import Warning


class WarningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warning_id: str
    assessment_id: str
    severity: str
    completeness: str
    risk_label: str
    explanation: str
    content_version: str
    created_at: datetime
    dispatched_at: datetime | None
    presented_at: datetime | None
    execution_mode: str

    @classmethod
    def from_warning(cls, warning: Warning) -> WarningResponse:
        return cls(
            warning_id=str(warning.warning_id),
            assessment_id=str(warning.assessment_id),
            severity=warning.severity.value,
            completeness=warning.completeness.value,
            risk_label=warning.risk_label,
            explanation=warning.explanation,
            content_version=warning.content_version,
            created_at=warning.created_at,
            dispatched_at=warning.dispatched_at,
            presented_at=warning.presented_at,
            execution_mode=warning.execution_mode.value,
        )


class WarningLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warning: WarningResponse | None
