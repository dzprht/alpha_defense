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
from alpha_defense.domain.identity import (
    ConsentScope,
    ConsentSnapshot,
    DemoSession,
    PreSession,
    SyntheticUser,
)
from alpha_defense.domain.shared import EntityId


@dataclass(slots=True)
class InMemoryState:
    users: dict[EntityId, SyntheticUser] = field(default_factory=dict)
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

    def clone(self) -> InMemoryState:
        return deepcopy(self)


class InMemoryDatabase:
    """A serializable process-local database shared by UnitOfWork instances."""

    def __init__(self) -> None:
        self.lock = RLock()
        self.state = InMemoryState()
