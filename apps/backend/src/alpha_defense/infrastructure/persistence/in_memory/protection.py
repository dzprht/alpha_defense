"""Copy-on-write warning repository."""

from __future__ import annotations

from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.domain.protection import Warning
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryState


class InMemoryWarningRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get(self, warning_id: EntityId) -> Warning | None:
        return self._state.warnings.get(warning_id)

    def get_by_assessment(self, assessment_id: EntityId) -> Warning | None:
        warning_id = self._state.warning_by_assessment.get(assessment_id)
        return None if warning_id is None else self.get(warning_id)

    def list_dispatched(self, *, owner_id: EntityId, namespace_id: EntityId) -> tuple[Warning, ...]:
        return tuple(
            sorted(
                (
                    warning
                    for warning in self._state.warnings.values()
                    if warning.owner_id == owner_id
                    and warning.namespace_id == namespace_id
                    and warning.dispatched_at is not None
                ),
                key=lambda warning: (warning.created_at, str(warning.warning_id)),
            )
        )

    def add(self, warning: Warning) -> None:
        if warning.warning_id in self._state.warnings or self.get_by_assessment(
            warning.assessment_id
        ):
            raise ValueError("warning or assessment already exists")
        self._state.warnings[warning.warning_id] = warning
        self._state.warning_by_assessment[warning.assessment_id] = warning.warning_id

    def save(self, warning: Warning, *, expected_revision: int) -> None:
        current = self.get(warning.warning_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Warning revision is stale")
        if warning.revision != expected_revision + 1:
            raise StaleRevisionError("Warning revision must advance by one")
        current.assert_successor(warning)
        self._state.warnings[warning.warning_id] = warning
