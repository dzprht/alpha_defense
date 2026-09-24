"""Immutable assessment storage within the contact transaction boundary."""

from __future__ import annotations

from typing import Protocol

from alpha_defense.application.ports.incidents import IncidentUnitOfWorkPort
from alpha_defense.application.ports.protection import WarningUnitOfWorkPort
from alpha_defense.domain.detection import RiskAssessment
from alpha_defense.domain.identity import ConsentScope, ConsentSnapshot
from alpha_defense.domain.shared import EntityId


class AssessmentRepositoryPort(Protocol):
    def get(self, assessment_id: EntityId) -> RiskAssessment | None: ...

    def list_for_observation(self, observation_id: EntityId) -> tuple[RiskAssessment, ...]: ...

    def add(self, assessment: RiskAssessment) -> None: ...


class ConsentReaderPort(Protocol):
    def get_consent(self, user_id: EntityId, scope: ConsentScope) -> ConsentSnapshot | None: ...


class ContactUnitOfWorkPort(IncidentUnitOfWorkPort, WarningUnitOfWorkPort, Protocol):
    @property
    def assessments(self) -> AssessmentRepositoryPort: ...

    @property
    def identity(self) -> ConsentReaderPort: ...


class ContactUnitOfWorkFactory(Protocol):
    def __call__(self) -> ContactUnitOfWorkPort: ...
