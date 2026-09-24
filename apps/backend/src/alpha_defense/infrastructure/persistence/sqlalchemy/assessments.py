"""SQLite storage for immutable, fully versioned assessment snapshots."""

from __future__ import annotations

import sqlalchemy as sa
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.shared import ServiceUnavailableError
from alpha_defense.domain.detection import RiskAssessment
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.persistence.sqlalchemy.schema import assessments

_CODEC = TypeAdapter(RiskAssessment)


class SqlAlchemyAssessmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, assessment_id: EntityId) -> RiskAssessment | None:
        row = (
            self._session.execute(
                sa.select(assessments).where(assessments.c.assessment_id == str(assessment_id))
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _decode(row)

    def list_for_observation(self, observation_id: EntityId) -> tuple[RiskAssessment, ...]:
        rows = self._session.execute(
            sa.select(assessments)
            .where(assessments.c.target_id == str(observation_id))
            .order_by(assessments.c.assessed_at, assessments.c.assessment_id)
        ).mappings()
        return tuple(_decode(row) for row in rows)

    def add(self, assessment: RiskAssessment) -> None:
        try:
            self._session.execute(
                sa.insert(assessments).values(
                    assessment_id=str(assessment.assessment_id),
                    owner_id=str(assessment.owner_id),
                    session_id=str(assessment.session_id),
                    namespace_id=str(assessment.namespace_id),
                    target_kind=assessment.target_kind.value,
                    target_id=str(assessment.target_id),
                    context_version=assessment.context_version,
                    assessed_at=assessment.assessed_at,
                    payload_json=_CODEC.dump_json(assessment).decode("utf-8"),
                )
            )
        except SQLAlchemyError as exc:
            raise ServiceUnavailableError("Local assessment persistence failed") from exc


def _decode(row: sa.RowMapping) -> RiskAssessment:
    try:
        assessment = _CODEC.validate_json(row["payload_json"])
    except (ValidationError, TypeError, ValueError) as exc:
        raise ServiceUnavailableError("Stored assessment is invalid") from exc
    if (
        str(assessment.assessment_id) != row["assessment_id"]
        or str(assessment.owner_id) != row["owner_id"]
        or str(assessment.session_id) != row["session_id"]
        or str(assessment.namespace_id) != row["namespace_id"]
        or assessment.target_kind.value != row["target_kind"]
        or str(assessment.target_id) != row["target_id"]
        or assessment.context_version != row["context_version"]
    ):
        raise ServiceUnavailableError("Stored assessment metadata differs from payload")
    return assessment
