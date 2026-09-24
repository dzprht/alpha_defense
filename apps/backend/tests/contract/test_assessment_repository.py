"""The in-memory assessment adapter preserves immutable snapshots and UoW rollback."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from alpha_defense.domain.detection import (
    AssessmentCompleteness,
    AssessmentTargetKind,
    RiskAssessment,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode, Provenance, Severity
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory


def _id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


def test_in_memory_assessments_commit_are_immutable_and_rollback() -> None:
    factory = InMemoryUnitOfWorkFactory()
    assessment = RiskAssessment(
        assessment_id=_id(1),
        owner_id=_id(2),
        session_id=_id(3),
        namespace_id=_id(4),
        target_kind=AssessmentTargetKind.OBSERVATION,
        target_id=_id(5),
        severity=Severity.UNKNOWN,
        score=None,
        score_kind="heuristic",
        completeness=AssessmentCompleteness.UNAVAILABLE,
        signals=(),
        applied_modifiers=(),
        reason_codes=("analyzer_unavailable",),
        analyzer_results=(),
        policy_version="demo-risk-v1",
        analysis_plan_version="observation-v1",
        assessed_at=datetime(2026, 9, 24, tzinfo=UTC),
        context_version=1,
        provenance=Provenance(ExecutionMode.MOCK, "test", "1", "1"),
        has_mock_evidence=True,
    )
    with factory() as uow:
        uow.assessments.add(assessment)
        assert uow.assessments.get(assessment.assessment_id) == assessment
    with factory() as uow:
        assert uow.assessments.get(assessment.assessment_id) is None
        uow.assessments.add(assessment)
        uow.commit()
    with factory() as uow:
        assert uow.assessments.list_for_observation(assessment.target_id) == (assessment,)
        with pytest.raises(ValueError, match="already exists"):
            uow.assessments.add(assessment)
