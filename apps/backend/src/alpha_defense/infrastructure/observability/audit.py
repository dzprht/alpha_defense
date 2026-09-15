"""Immutable audit writer scoped to an active local transaction."""

from alpha_defense.application.ports import (
    AuditReceipt,
    AuditRecord,
    AuditRepositoryPort,
    Clock,
    EventEnvelope,
)
from alpha_defense.domain.shared import EntityId


class TransactionalAuditWriter:
    def __init__(self, repository: AuditRepositoryPort, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def append(
        self,
        event: EventEnvelope,
        *,
        actor_id: EntityId | None,
        session_id: EntityId | None,
        namespace_id: EntityId | None,
    ) -> AuditReceipt:
        recorded_at = self._clock.now_utc()
        self._repository.append(
            AuditRecord(
                event=event,
                actor_id=actor_id,
                session_id=session_id,
                namespace_id=namespace_id,
                recorded_at=recorded_at,
            )
        )
        return AuditReceipt(event_id=event.event_id, recorded_at=recorded_at)
