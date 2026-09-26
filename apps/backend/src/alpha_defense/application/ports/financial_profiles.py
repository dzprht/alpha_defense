"""Owner-scoped synthetic profile persistence and trusted template contracts."""

from __future__ import annotations

from typing import Protocol

from alpha_defense.application.ports.unit_of_work import UnitOfWorkPort
from alpha_defense.domain.identity import ConsentScope, ConsentSnapshot
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.transfers import FinancialProfile


class ProfileRepositoryPort(Protocol):
    def get(self, profile_id: EntityId) -> FinancialProfile | None: ...

    def get_by_template(
        self, *, owner_id: EntityId, namespace_id: EntityId, template_code: str
    ) -> FinancialProfile | None: ...

    def list_owned(
        self, *, owner_id: EntityId, namespace_id: EntityId
    ) -> tuple[FinancialProfile, ...]: ...

    def add(self, profile: FinancialProfile) -> None: ...

    def append_completed(self, profile: FinancialProfile, *, expected_version: int) -> None: ...


class ProfileConsentReaderPort(Protocol):
    def get_consent(self, user_id: EntityId, scope: ConsentScope) -> ConsentSnapshot | None: ...


class ProfileUnitOfWorkPort(UnitOfWorkPort, Protocol):
    @property
    def profiles(self) -> ProfileRepositoryPort: ...

    @property
    def identity(self) -> ProfileConsentReaderPort: ...


class ProfileUnitOfWorkFactory(Protocol):
    def __call__(self) -> ProfileUnitOfWorkPort: ...
