"""Serializable copy-on-write UnitOfWork for the in-memory adapter."""

from __future__ import annotations

from types import TracebackType

from alpha_defense.infrastructure.persistence.in_memory.repositories import (
    InMemoryAuditRepository,
    InMemoryIdempotencyRepository,
    InMemoryIdentityRepository,
    InMemoryOutboxRepository,
)
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryDatabase, InMemoryState
from alpha_defense.infrastructure.persistence.in_memory.threat_registry import (
    InMemoryThreatRegistryRepository,
)


class InMemoryUnitOfWork:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database
        self._state: InMemoryState | None = None
        self._active = False
        self._finished = False
        self._idempotency: InMemoryIdempotencyRepository | None = None
        self._identity: InMemoryIdentityRepository | None = None
        self._audit: InMemoryAuditRepository | None = None
        self._outbox: InMemoryOutboxRepository | None = None
        self._threat_registry: InMemoryThreatRegistryRepository | None = None

    @property
    def idempotency(self) -> InMemoryIdempotencyRepository:
        if self._idempotency is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._idempotency

    @property
    def audit(self) -> InMemoryAuditRepository:
        if self._audit is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._audit

    @property
    def identity(self) -> InMemoryIdentityRepository:
        if self._identity is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._identity

    @property
    def outbox(self) -> InMemoryOutboxRepository:
        if self._outbox is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._outbox

    @property
    def threat_registry(self) -> InMemoryThreatRegistryRepository:
        if self._threat_registry is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._threat_registry

    def begin(self) -> None:
        if self._active:
            raise RuntimeError("UnitOfWork is already active")
        self._database.lock.acquire()
        self._state = self._database.state.clone()
        self._idempotency = InMemoryIdempotencyRepository(self._state)
        self._identity = InMemoryIdentityRepository(self._state)
        self._audit = InMemoryAuditRepository(self._state)
        self._outbox = InMemoryOutboxRepository(self._state)
        self._threat_registry = InMemoryThreatRegistryRepository(self._state)
        self._active = True
        self._finished = False

    def commit(self) -> None:
        state = self._require_unfinished()
        self._database.state = state.clone()
        self._finish()

    def rollback(self) -> None:
        self._require_active()
        if not self._finished:
            self._finish()

    def __enter__(self) -> InMemoryUnitOfWork:
        self.begin()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._active and not self._finished:
            self.rollback()

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("UnitOfWork is not active")

    def _require_unfinished(self) -> InMemoryState:
        self._require_active()
        if self._finished or self._state is None:
            raise RuntimeError("UnitOfWork transaction is already finished")
        return self._state

    def _finish(self) -> None:
        self._finished = True
        self._active = False
        self._database.lock.release()


class InMemoryUnitOfWorkFactory:
    def __init__(self, database: InMemoryDatabase | None = None) -> None:
        self.database = database or InMemoryDatabase()

    def __call__(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self.database)
