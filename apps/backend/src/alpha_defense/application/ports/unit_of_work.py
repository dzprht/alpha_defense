"""Local transaction boundary used by application workflows."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from alpha_defense.application.ports.repositories import (
    AuditRepositoryPort,
    IdempotencyRepositoryPort,
    OutboxRepositoryPort,
)


class UnitOfWorkPort(Protocol):
    @property
    def idempotency(self) -> IdempotencyRepositoryPort: ...

    @property
    def audit(self) -> AuditRepositoryPort: ...

    @property
    def outbox(self) -> OutboxRepositoryPort: ...

    def begin(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWorkPort: ...
