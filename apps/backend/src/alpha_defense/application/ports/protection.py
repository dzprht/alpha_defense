"""Storage boundary for in-app warning state."""

from __future__ import annotations

from typing import Protocol

from alpha_defense.application.ports.unit_of_work import UnitOfWorkPort
from alpha_defense.domain.protection import Warning
from alpha_defense.domain.shared import EntityId


class WarningRepositoryPort(Protocol):
    def get(self, warning_id: EntityId) -> Warning | None: ...

    def get_by_assessment(self, assessment_id: EntityId) -> Warning | None: ...

    def list_dispatched(
        self, *, owner_id: EntityId, session_id: EntityId, namespace_id: EntityId
    ) -> tuple[Warning, ...]: ...

    def add(self, warning: Warning) -> None: ...

    def save(self, warning: Warning, *, expected_revision: int) -> None: ...


class WarningUnitOfWorkPort(UnitOfWorkPort, Protocol):
    @property
    def warnings(self) -> WarningRepositoryPort: ...


class WarningUnitOfWorkFactory(Protocol):
    def __call__(self) -> WarningUnitOfWorkPort: ...
