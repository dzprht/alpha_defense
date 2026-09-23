"""SQLite persistence for incidents, timeline history, and risk freshness."""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult, Result, RowMapping
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.shared import ServiceUnavailableError, StaleRevisionError
from alpha_defense.domain.incidents import (
    CorrelationKey,
    CorrelationKeyKind,
    CorrelationReason,
    Incident,
    IncidentAssessmentLink,
    IncidentObservationLink,
    IncidentResolution,
    IncidentResolutionCode,
    IncidentStatus,
    NamespaceRiskState,
    PendingAnalysis,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode
from alpha_defense.infrastructure.persistence.sqlalchemy.mappers import as_utc
from alpha_defense.infrastructure.persistence.sqlalchemy.schema import (
    incident_assessments,
    incident_correlation_keys,
    incident_observations,
    incident_resolutions,
    incidents,
    namespace_pending_analyses,
    namespace_risk_states,
)


class SqlAlchemyIncidentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, incident_id: EntityId) -> Incident | None:
        row = (
            _execute(
                self._session,
                sa.select(incidents).where(incidents.c.incident_id == str(incident_id)),
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._from_row(row)

    def get_by_observation(self, observation_id: EntityId) -> Incident | None:
        incident_id = _execute(
            self._session,
            sa.select(incident_observations.c.incident_id).where(
                incident_observations.c.observation_id == str(observation_id)
            ),
        ).scalar_one_or_none()
        return None if incident_id is None else self.get(EntityId.from_string(incident_id))

    def list_for_scope(
        self,
        *,
        owner_id: EntityId,
        namespace_id: EntityId,
    ) -> tuple[Incident, ...]:
        rows = _execute(
            self._session,
            sa.select(incidents)
            .where(
                incidents.c.owner_id == str(owner_id),
                incidents.c.namespace_id == str(namespace_id),
            )
            .order_by(incidents.c.updated_at, incidents.c.incident_id),
        ).mappings()
        return tuple(self._from_row(row) for row in rows)

    def add(self, incident: Incident) -> None:
        _execute(self._session, sa.insert(incidents).values(_incident_values(incident)))
        self._append_history(incident, observation_start=0, assessment_start=0, resolution_start=0)

    def save(self, incident: Incident, *, expected_revision: int) -> None:
        current = self.get(incident.incident_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Incident revision is stale")
        if incident.revision != expected_revision + 1:
            raise StaleRevisionError("Incident revision must advance by one")
        _assert_incident_update(current, incident)
        result = _execute(
            self._session,
            sa.update(incidents)
            .where(
                incidents.c.incident_id == str(incident.incident_id),
                incidents.c.revision == expected_revision,
            )
            .values(
                status=incident.status.value,
                latest_assessment_id=(
                    None
                    if incident.latest_assessment_id is None
                    else str(incident.latest_assessment_id)
                ),
                current_resolution_code=(
                    None if incident.resolution is None else incident.resolution.code.value
                ),
                context_version=incident.context_version,
                revision=incident.revision,
                updated_at=incident.updated_at,
            ),
        )
        if _rowcount(result) != 1:
            raise StaleRevisionError("Incident revision is stale")
        self._append_history(
            incident,
            observation_start=len(current.observation_links),
            assessment_start=len(current.assessment_links),
            resolution_start=len(current.resolution_history),
        )

    def _append_history(
        self,
        incident: Incident,
        *,
        observation_start: int,
        assessment_start: int,
        resolution_start: int,
    ) -> None:
        new_observations = incident.observation_links[observation_start:]
        if new_observations:
            _execute(
                self._session,
                sa.insert(incident_observations).values(
                    [
                        _observation_link_values(incident.incident_id, ordinal, link)
                        for ordinal, link in enumerate(
                            new_observations,
                            start=observation_start,
                        )
                    ]
                ),
            )
            key_values = [
                {
                    "incident_id": str(incident.incident_id),
                    "observation_id": str(link.observation_id),
                    "key_kind": key.kind.value,
                    "key_value": key.value,
                }
                for link in new_observations
                for key in link.available_keys
            ]
            if key_values:
                _execute(
                    self._session,
                    sa.insert(incident_correlation_keys).values(key_values),
                )
        new_assessments = incident.assessment_links[assessment_start:]
        if new_assessments:
            _execute(
                self._session,
                sa.insert(incident_assessments).values(
                    [
                        {
                            "incident_id": str(incident.incident_id),
                            "ordinal": ordinal,
                            "assessment_id": str(link.assessment_id),
                            "assessed_at": link.assessed_at,
                            "context_version": link.context_version,
                        }
                        for ordinal, link in enumerate(
                            new_assessments,
                            start=assessment_start,
                        )
                    ]
                ),
            )
        new_resolutions = incident.resolution_history[resolution_start:]
        if new_resolutions:
            _execute(
                self._session,
                sa.insert(incident_resolutions).values(
                    [
                        {
                            "incident_id": str(incident.incident_id),
                            "ordinal": ordinal,
                            "resolution_code": item.code.value,
                            "resolved_at": item.resolved_at,
                            "resolved_by": str(item.resolved_by),
                            "context_version": item.context_version,
                        }
                        for ordinal, item in enumerate(
                            new_resolutions,
                            start=resolution_start,
                        )
                    ]
                ),
            )

    def _from_row(self, row: RowMapping) -> Incident:
        incident_id = row["incident_id"]
        observation_rows = tuple(
            _execute(
                self._session,
                sa.select(incident_observations)
                .where(incident_observations.c.incident_id == incident_id)
                .order_by(incident_observations.c.ordinal),
            ).mappings()
        )
        key_rows = tuple(
            _execute(
                self._session,
                sa.select(incident_correlation_keys)
                .where(incident_correlation_keys.c.incident_id == incident_id)
                .order_by(
                    incident_correlation_keys.c.observation_id,
                    incident_correlation_keys.c.key_kind,
                    incident_correlation_keys.c.key_value,
                ),
            ).mappings()
        )
        keys_by_observation: dict[str, list[CorrelationKey]] = {}
        for key_row in key_rows:
            keys_by_observation.setdefault(key_row["observation_id"], []).append(
                CorrelationKey(
                    kind=CorrelationKeyKind(key_row["key_kind"]),
                    value=key_row["key_value"],
                )
            )
        observation_links = tuple(
            _observation_link_from_row(
                item,
                tuple(keys_by_observation.get(item["observation_id"], ())),
            )
            for item in observation_rows
        )
        assessment_links = tuple(
            IncidentAssessmentLink(
                assessment_id=EntityId.from_string(item["assessment_id"]),
                assessed_at=as_utc(item["assessed_at"]),
                context_version=item["context_version"],
            )
            for item in _execute(
                self._session,
                sa.select(incident_assessments)
                .where(incident_assessments.c.incident_id == incident_id)
                .order_by(incident_assessments.c.ordinal),
            ).mappings()
        )
        resolutions = tuple(
            IncidentResolution(
                code=IncidentResolutionCode(item["resolution_code"]),
                resolved_at=as_utc(item["resolved_at"]),
                resolved_by=EntityId.from_string(item["resolved_by"]),
                context_version=item["context_version"],
            )
            for item in _execute(
                self._session,
                sa.select(incident_resolutions)
                .where(incident_resolutions.c.incident_id == incident_id)
                .order_by(incident_resolutions.c.ordinal),
            ).mappings()
        )
        incident = Incident(
            incident_id=EntityId.from_string(incident_id),
            owner_id=EntityId.from_string(row["owner_id"]),
            session_id=EntityId.from_string(row["session_id"]),
            namespace_id=EntityId.from_string(row["namespace_id"]),
            status=IncidentStatus(row["status"]),
            observation_links=observation_links,
            assessment_links=assessment_links,
            resolution_history=resolutions,
            context_version=row["context_version"],
            revision=row["revision"],
            created_at=as_utc(row["created_at"]),
            updated_at=as_utc(row["updated_at"]),
            execution_mode=ExecutionMode(row["execution_mode"]),
        )
        persisted_latest = row["latest_assessment_id"]
        expected_latest = (
            None if incident.latest_assessment_id is None else str(incident.latest_assessment_id)
        )
        persisted_resolution = row["current_resolution_code"]
        expected_resolution = (
            None if incident.resolution is None else incident.resolution.code.value
        )
        if persisted_latest != expected_latest or persisted_resolution != expected_resolution:
            raise ServiceUnavailableError("Persisted incident history is inconsistent")
        return incident


class SqlAlchemyNamespaceRiskStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, namespace_id: EntityId) -> NamespaceRiskState | None:
        row = (
            _execute(
                self._session,
                sa.select(namespace_risk_states).where(
                    namespace_risk_states.c.namespace_id == str(namespace_id)
                ),
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        pending = tuple(
            PendingAnalysis(
                observation_id=EntityId.from_string(item["observation_id"]),
                incident_id=EntityId.from_string(item["incident_id"]),
                accepted_at=as_utc(item["accepted_at"]),
            )
            for item in _execute(
                self._session,
                sa.select(namespace_pending_analyses)
                .where(namespace_pending_analyses.c.namespace_id == str(namespace_id))
                .order_by(
                    namespace_pending_analyses.c.accepted_at,
                    namespace_pending_analyses.c.observation_id,
                ),
            ).mappings()
        )
        return NamespaceRiskState(
            namespace_id=EntityId.from_string(row["namespace_id"]),
            owner_id=EntityId.from_string(row["owner_id"]),
            session_id=EntityId.from_string(row["session_id"]),
            ingress_risk_epoch=row["ingress_risk_epoch"],
            pending_analyses=pending,
            revision=row["revision"],
            updated_at=as_utc(row["updated_at"]),
            execution_mode=ExecutionMode(row["execution_mode"]),
        )

    def add(self, state: NamespaceRiskState) -> None:
        _execute(
            self._session,
            sa.insert(namespace_risk_states).values(_risk_state_values(state)),
        )
        self._replace_pending(state)

    def save(self, state: NamespaceRiskState, *, expected_revision: int) -> None:
        current = self.get(state.namespace_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Namespace risk state revision is stale")
        if state.revision != expected_revision + 1:
            raise StaleRevisionError("Namespace risk state revision must advance by one")
        if (
            current.owner_id != state.owner_id
            or current.session_id != state.session_id
            or current.execution_mode is not state.execution_mode
            or state.ingress_risk_epoch < current.ingress_risk_epoch
        ):
            raise ValueError("immutable namespace risk state fields cannot be changed")
        result = _execute(
            self._session,
            sa.update(namespace_risk_states)
            .where(
                namespace_risk_states.c.namespace_id == str(state.namespace_id),
                namespace_risk_states.c.revision == expected_revision,
            )
            .values(
                ingress_risk_epoch=state.ingress_risk_epoch,
                revision=state.revision,
                updated_at=state.updated_at,
            ),
        )
        if _rowcount(result) != 1:
            raise StaleRevisionError("Namespace risk state revision is stale")
        self._replace_pending(state)

    def _replace_pending(self, state: NamespaceRiskState) -> None:
        _execute(
            self._session,
            sa.delete(namespace_pending_analyses).where(
                namespace_pending_analyses.c.namespace_id == str(state.namespace_id)
            ),
        )
        if state.pending_analyses:
            _execute(
                self._session,
                sa.insert(namespace_pending_analyses).values(
                    [
                        {
                            "namespace_id": str(state.namespace_id),
                            "observation_id": str(item.observation_id),
                            "incident_id": str(item.incident_id),
                            "accepted_at": item.accepted_at,
                        }
                        for item in state.pending_analyses
                    ]
                ),
            )


def _incident_values(incident: Incident) -> dict[str, Any]:
    return {
        "incident_id": str(incident.incident_id),
        "owner_id": str(incident.owner_id),
        "session_id": str(incident.session_id),
        "namespace_id": str(incident.namespace_id),
        "status": incident.status.value,
        "latest_assessment_id": (
            None if incident.latest_assessment_id is None else str(incident.latest_assessment_id)
        ),
        "current_resolution_code": (
            None if incident.resolution is None else incident.resolution.code.value
        ),
        "context_version": incident.context_version,
        "revision": incident.revision,
        "created_at": incident.created_at,
        "updated_at": incident.updated_at,
        "execution_mode": incident.execution_mode.value,
    }


def _observation_link_values(
    incident_id: EntityId,
    ordinal: int,
    link: IncidentObservationLink,
) -> dict[str, Any]:
    return {
        "incident_id": str(incident_id),
        "ordinal": ordinal,
        "observation_id": str(link.observation_id),
        "attached_at": link.attached_at,
        "context_version": link.context_version,
        "correlation_reason": link.correlation_reason.value,
        "correlation_key_kind": (
            None if link.correlation_key is None else link.correlation_key.kind.value
        ),
        "correlation_key_value": (
            None if link.correlation_key is None else link.correlation_key.value
        ),
    }


def _observation_link_from_row(
    row: RowMapping,
    keys: tuple[CorrelationKey, ...],
) -> IncidentObservationLink:
    key_kind = row["correlation_key_kind"]
    key_value = row["correlation_key_value"]
    selected = (
        None
        if key_kind is None
        else CorrelationKey(kind=CorrelationKeyKind(key_kind), value=key_value)
    )
    return IncidentObservationLink(
        observation_id=EntityId.from_string(row["observation_id"]),
        attached_at=as_utc(row["attached_at"]),
        context_version=row["context_version"],
        correlation_reason=CorrelationReason(row["correlation_reason"]),
        correlation_key=selected,
        available_keys=keys,
    )


def _risk_state_values(state: NamespaceRiskState) -> dict[str, Any]:
    return {
        "namespace_id": str(state.namespace_id),
        "owner_id": str(state.owner_id),
        "session_id": str(state.session_id),
        "ingress_risk_epoch": state.ingress_risk_epoch,
        "revision": state.revision,
        "updated_at": state.updated_at,
        "execution_mode": state.execution_mode.value,
    }


def _assert_incident_update(current: Incident, updated: Incident) -> None:
    if (
        current.owner_id != updated.owner_id
        or current.session_id != updated.session_id
        or current.namespace_id != updated.namespace_id
        or current.created_at != updated.created_at
        or current.execution_mode is not updated.execution_mode
    ):
        raise ValueError("immutable incident fields cannot be changed")
    if (
        updated.observation_links[: len(current.observation_links)] != current.observation_links
        or updated.assessment_links[: len(current.assessment_links)] != current.assessment_links
        or updated.resolution_history[: len(current.resolution_history)]
        != current.resolution_history
    ):
        raise ValueError("incident timeline history is append-only")


def _rowcount(result: Result[Any]) -> int:
    return cast(CursorResult[Any], result).rowcount


def _execute(session: Session, statement: Any) -> Result[Any]:
    try:
        return session.execute(statement)
    except IntegrityError as exc:
        raise ValueError("persistence constraint rejected the incident") from exc
    except SQLAlchemyError as exc:
        raise ServiceUnavailableError("Local persistence is unavailable") from exc
