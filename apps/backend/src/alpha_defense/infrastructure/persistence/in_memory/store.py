"""Shared state and serialization lock for the in-memory adapter."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock

from alpha_defense.application.ports import (
    AuditRecord,
    IdempotencyRecord,
    IdempotencyScope,
    OutboxMessage,
)
from alpha_defense.domain.communications import Observation, ObservationContent
from alpha_defense.domain.detection import RiskAssessment
from alpha_defense.domain.identity import (
    Account,
    ConsentScope,
    ConsentSnapshot,
    DemoSession,
    LoginThrottle,
    PreSession,
    SyntheticUser,
)
from alpha_defense.domain.incidents import Incident, NamespaceRiskState
from alpha_defense.domain.protection import Warning
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import RegistrySnapshot
from alpha_defense.domain.transfers import FinancialProfile


@dataclass(slots=True)
class InMemoryState:
    users: dict[EntityId, SyntheticUser] = field(default_factory=dict)
    accounts: dict[EntityId, Account] = field(default_factory=dict)
    account_logins: dict[str, EntityId] = field(default_factory=dict)
    login_throttles: dict[str, LoginThrottle] = field(default_factory=dict)
    pre_sessions: dict[EntityId, PreSession] = field(default_factory=dict)
    pre_session_tokens: dict[str, EntityId] = field(default_factory=dict)
    sessions: dict[EntityId, DemoSession] = field(default_factory=dict)
    session_tokens: dict[str, EntityId] = field(default_factory=dict)
    session_namespaces: dict[EntityId, EntityId] = field(default_factory=dict)
    consents: dict[tuple[EntityId, ConsentScope], ConsentSnapshot] = field(default_factory=dict)
    idempotency_records: dict[EntityId, IdempotencyRecord] = field(default_factory=dict)
    idempotency_scopes: dict[IdempotencyScope, EntityId] = field(default_factory=dict)
    audit_events: dict[EntityId, AuditRecord] = field(default_factory=dict)
    outbox_messages: dict[EntityId, OutboxMessage] = field(default_factory=dict)
    outbox_events: dict[tuple[EntityId, str], EntityId] = field(default_factory=dict)
    threat_snapshots: dict[EntityId, RegistrySnapshot] = field(default_factory=dict)
    threat_snapshot_versions: dict[str, EntityId] = field(default_factory=dict)
    current_threat_snapshot_id: EntityId | None = None
    observations: dict[EntityId, Observation] = field(default_factory=dict)
    observation_contents: dict[EntityId, ObservationContent] = field(default_factory=dict)
    observation_source_events: dict[tuple[EntityId, str, str], EntityId] = field(
        default_factory=dict
    )
    incidents: dict[EntityId, Incident] = field(default_factory=dict)
    incidents_by_observation: dict[EntityId, EntityId] = field(default_factory=dict)
    namespace_risk_states: dict[EntityId, NamespaceRiskState] = field(default_factory=dict)
    assessments: dict[EntityId, RiskAssessment] = field(default_factory=dict)
    warnings: dict[EntityId, Warning] = field(default_factory=dict)
    warning_by_assessment: dict[EntityId, EntityId] = field(default_factory=dict)
    financial_profiles: dict[EntityId, FinancialProfile] = field(default_factory=dict)
    profile_templates: dict[tuple[EntityId, EntityId, str], EntityId] = field(default_factory=dict)

    def clone(self) -> InMemoryState:
        return deepcopy(self)


class InMemoryDatabase:
    """A serializable process-local database shared by UnitOfWork instances."""

    def __init__(self) -> None:
        self.lock = RLock()
        self.state = InMemoryState()
