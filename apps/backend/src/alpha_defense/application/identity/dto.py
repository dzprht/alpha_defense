"""Transport-neutral identity views and token delivery results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alpha_defense.application.shared import ActorRole
from alpha_defense.domain.identity import ConsentScope, ConsentSnapshot, ConsentStatus, DemoSession
from alpha_defense.domain.shared import EntityId, ExecutionMode


@dataclass(frozen=True, slots=True)
class ConsentView:
    scope: ConsentScope
    status: ConsentStatus
    revision: int
    changed_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: ConsentSnapshot) -> ConsentView:
        return cls(
            scope=snapshot.scope,
            status=snapshot.status,
            revision=snapshot.revision,
            changed_at=snapshot.changed_at,
        )


@dataclass(frozen=True, slots=True)
class AnonymousSessionView:
    pre_session_expires_at: datetime
    execution_mode: ExecutionMode
    capabilities: tuple[str, ...] = ("start_demo_session",)


@dataclass(frozen=True, slots=True)
class SessionView:
    user_id: EntityId
    session_id: EntityId
    namespace_id: EntityId
    roles: tuple[ActorRole, ...]
    consent_revision: int
    consents: tuple[ConsentView, ...]
    execution_mode: ExecutionMode
    expires_at: datetime
    capabilities: tuple[str, ...] = ("update_consents",)

    @classmethod
    def from_session(
        cls,
        session: DemoSession,
        consents: tuple[ConsentSnapshot, ...],
        *,
        execution_mode: ExecutionMode,
    ) -> SessionView:
        roles = tuple(sorted((ActorRole(role.value) for role in session.roles), key=str))
        return cls(
            user_id=session.user_id,
            session_id=session.session_id,
            namespace_id=session.manual_namespace_id,
            roles=roles,
            consent_revision=session.consent_revision,
            consents=tuple(ConsentView.from_snapshot(item) for item in consents),
            execution_mode=execution_mode,
            expires_at=session.expires_at,
        )


@dataclass(frozen=True, slots=True)
class SessionBootstrapResult:
    view: AnonymousSessionView | SessionView
    csrf_token: str
    pre_session_token: str | None = None
    session_token: str | None = None


@dataclass(frozen=True, slots=True)
class StartSessionResult:
    view: SessionView
    session_token: str
    csrf_token: str
    replayed: bool
