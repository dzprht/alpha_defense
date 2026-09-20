"""Incident state, correlation, history, and freshness invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from alpha_defense.domain.incidents import (
    CorrelationKey,
    CorrelationKeyKind,
    CorrelationReason,
    Incident,
    IncidentResolutionCode,
    IncidentStatus,
    IncidentTimelineItemKind,
    NamespaceRiskState,
    PreliminaryCorrelationPolicy,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


def _key(kind: CorrelationKeyKind, value: str) -> CorrelationKey:
    return CorrelationKey(kind=kind, value=value)


def _incident(*, incident_id: int = 10, observation_id: int = 20) -> Incident:
    return Incident.create(
        incident_id=_id(incident_id),
        owner_id=_id(1),
        session_id=_id(2),
        namespace_id=_id(3),
        observation_id=_id(observation_id),
        available_keys=(
            _key(CorrelationKeyKind.CONVERSATION, "conversation-1"),
            _key(CorrelationKeyKind.INDICATOR, "domain:example.test"),
        ),
        created_at=NOW,
        execution_mode=ExecutionMode.MOCK,
    )


def test_incident_history_is_append_only_and_reopens_on_new_evidence() -> None:
    incident = _incident()
    assessed = incident.record_assessment(
        assessment_id=_id(30),
        context_version=1,
        assessed_at=NOW + timedelta(seconds=1),
    )
    resolved = assessed.resolve(
        code=IncidentResolutionCode.FALSE_POSITIVE_REPORTED,
        resolved_at=NOW + timedelta(seconds=2),
        resolved_by=_id(1),
    )
    reopened = resolved.attach_observation(
        observation_id=_id(21),
        available_keys=(_key(CorrelationKeyKind.CONVERSATION, "conversation-1"),),
        correlation_reason=CorrelationReason.CONVERSATION,
        correlation_key=_key(CorrelationKeyKind.CONVERSATION, "conversation-1"),
        attached_at=NOW + timedelta(seconds=3),
    )

    assert reopened.status is IncidentStatus.OPEN
    assert reopened.context_version == 2
    assert reopened.assessment_ids == (_id(30),)
    assert reopened.resolution_history == resolved.resolution_history
    assert [item.kind for item in reopened.timeline()] == [
        IncidentTimelineItemKind.OBSERVATION,
        IncidentTimelineItemKind.ASSESSMENT,
        IncidentTimelineItemKind.RESOLUTION,
        IncidentTimelineItemKind.OBSERVATION,
    ]


def test_stale_assessment_and_invalid_correlation_are_rejected() -> None:
    incident = _incident()

    with pytest.raises(ValueError, match="context_version is stale"):
        incident.record_assessment(
            assessment_id=_id(30),
            context_version=2,
            assessed_at=NOW,
        )
    with pytest.raises(ValueError, match="reason does not match"):
        incident.attach_observation(
            observation_id=_id(21),
            available_keys=(_key(CorrelationKeyKind.INDICATOR, "domain:example.test"),),
            correlation_reason=CorrelationReason.CONVERSATION,
            correlation_key=_key(CorrelationKeyKind.INDICATOR, "domain:example.test"),
            attached_at=NOW,
        )


def test_resolved_incident_requires_new_evidence_before_assessment() -> None:
    incident = _incident().resolve(
        code=IncidentResolutionCode.NO_ACTION_NEEDED,
        resolved_at=NOW + timedelta(seconds=1),
        resolved_by=_id(1),
    )

    with pytest.raises(ValueError, match="require new evidence"):
        incident.record_assessment(
            assessment_id=_id(30),
            context_version=incident.context_version,
            assessed_at=NOW + timedelta(seconds=2),
        )


def test_correlation_prefers_explicit_identity_and_never_uses_time_alone() -> None:
    first = _incident(incident_id=10)
    second = Incident.create(
        incident_id=_id(11),
        owner_id=_id(1),
        session_id=_id(2),
        namespace_id=_id(3),
        observation_id=_id(22),
        available_keys=(
            _key(CorrelationKeyKind.CONVERSATION, "conversation-2"),
            _key(CorrelationKeyKind.INDICATOR, "domain:shared.test"),
        ),
        created_at=NOW,
        execution_mode=ExecutionMode.MOCK,
    )
    policy = PreliminaryCorrelationPolicy()

    explicit = policy.choose(
        candidates=(first, second),
        available_keys=(
            _key(CorrelationKeyKind.CONVERSATION, "conversation-1"),
            _key(CorrelationKeyKind.INDICATOR, "domain:shared.test"),
        ),
    )
    no_evidence = policy.choose(candidates=(first, second), available_keys=())

    assert explicit is not None
    assert explicit.incident_id == first.incident_id
    assert explicit.reason is CorrelationReason.CONVERSATION
    assert no_evidence is None


def test_namespace_risk_epoch_only_grows_on_new_ingress() -> None:
    state = NamespaceRiskState.create(
        namespace_id=_id(3),
        owner_id=_id(1),
        session_id=_id(2),
        observation_id=_id(20),
        incident_id=_id(10),
        accepted_at=NOW,
        execution_mode=ExecutionMode.MOCK,
    )
    updated = state.accept(
        observation_id=_id(21),
        incident_id=_id(10),
        accepted_at=NOW + timedelta(seconds=1),
    )
    completed = updated.complete(
        observation_id=_id(20),
        completed_at=NOW + timedelta(seconds=2),
    )

    assert state.ingress_risk_epoch == 1
    assert updated.ingress_risk_epoch == 2
    assert updated.analysis_pending
    assert completed.ingress_risk_epoch == 2
    assert completed.analysis_pending
    assert completed.is_pending(_id(21))


def test_namespace_risk_state_rejects_time_rollback() -> None:
    state = NamespaceRiskState.create(
        namespace_id=_id(3),
        owner_id=_id(1),
        session_id=_id(2),
        observation_id=_id(20),
        incident_id=_id(10),
        accepted_at=NOW,
        execution_mode=ExecutionMode.MOCK,
    )

    with pytest.raises(ValueError, match="accepted_at cannot precede"):
        state.accept(
            observation_id=_id(21),
            incident_id=_id(10),
            accepted_at=NOW - timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="completed_at cannot precede"):
        state.complete(
            observation_id=_id(20),
            completed_at=NOW - timedelta(seconds=1),
        )
