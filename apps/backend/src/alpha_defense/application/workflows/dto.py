"""Cross-feature workflow receipts."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_defense.application.communications import ObservationView
from alpha_defense.application.incidents import IncidentView, NamespaceRiskStateView


@dataclass(frozen=True, slots=True)
class AnalyzeContactReceipt:
    observation: ObservationView
    incident: IncidentView
    risk_state: NamespaceRiskStateView
    duplicate_source_event: bool
    created_incident: bool
