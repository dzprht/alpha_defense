"""Copy-on-write immutable assessment repository."""

from __future__ import annotations

from alpha_defense.domain.detection import RiskAssessment
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryState


class InMemoryAssessmentRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get(self, assessment_id: EntityId) -> RiskAssessment | None:
        return self._state.assessments.get(assessment_id)

    def list_for_observation(self, observation_id: EntityId) -> tuple[RiskAssessment, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._state.assessments.values()
                    if item.target_id == observation_id
                ),
                key=lambda item: (item.assessed_at, str(item.assessment_id)),
            )
        )

    def add(self, assessment: RiskAssessment) -> None:
        if assessment.assessment_id in self._state.assessments:
            raise ValueError("assessment already exists")
        self._state.assessments[assessment.assessment_id] = assessment
