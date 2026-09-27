"""Atomic draft and local-bank persistence contracts for transfers."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from alpha_defense.application.ports.assessments import AssessmentRepositoryPort
from alpha_defense.application.ports.financial_profiles import (
    ProfileConsentReaderPort,
    ProfileRepositoryPort,
)
from alpha_defense.application.ports.incidents import (
    IncidentRepositoryPort,
    NamespaceRiskStateRepositoryPort,
)
from alpha_defense.application.ports.threat_intel import ThreatRegistryRepositoryPort
from alpha_defense.application.ports.unit_of_work import UnitOfWorkPort
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.transfers import DemoBankResult, TransferCheck, TransferIntent


class TransferIntentRepositoryPort(Protocol):
    def get(self, intent_id: EntityId) -> TransferIntent | None: ...

    def list_owned(
        self, *, owner_id: EntityId, namespace_id: EntityId
    ) -> tuple[TransferIntent, ...]: ...

    def add(self, intent: TransferIntent) -> None: ...

    def save(self, intent: TransferIntent, *, expected_revision: int) -> None: ...

    def mark_checked(self, intent: TransferIntent, *, expected_revision: int) -> None: ...

    def finish(self, intent: TransferIntent, *, expected_revision: int) -> None: ...


class TransferCheckRepositoryPort(Protocol):
    def get(self, check_id: EntityId) -> TransferCheck | None: ...

    def get_latest_for_intent(self, intent_id: EntityId) -> TransferCheck | None: ...

    def list_for_intent(self, intent_id: EntityId) -> tuple[TransferCheck, ...]: ...

    def add(self, check: TransferCheck) -> None: ...


class DemoBankPort(Protocol):
    """A local-only operation; caller commits this result with the intent in one UoW."""

    def get_by_intent(self, intent_id: EntityId) -> DemoBankResult | None: ...

    def record(
        self, intent: TransferIntent, *, operation_id: EntityId, recorded_at: datetime
    ) -> DemoBankResult: ...


class TransferUnitOfWorkPort(UnitOfWorkPort, Protocol):
    @property
    def transfer_intents(self) -> TransferIntentRepositoryPort: ...

    @property
    def demo_bank(self) -> DemoBankPort: ...

    @property
    def profiles(self) -> ProfileRepositoryPort: ...

    @property
    def transfer_checks(self) -> TransferCheckRepositoryPort: ...

    @property
    def incidents(self) -> IncidentRepositoryPort: ...

    @property
    def namespace_risk_states(self) -> NamespaceRiskStateRepositoryPort: ...

    @property
    def assessments(self) -> AssessmentRepositoryPort: ...

    @property
    def threat_registry(self) -> ThreatRegistryRepositoryPort: ...

    @property
    def identity(self) -> ProfileConsentReaderPort: ...


class TransferUnitOfWorkFactory(Protocol):
    def __call__(self) -> TransferUnitOfWorkPort: ...
