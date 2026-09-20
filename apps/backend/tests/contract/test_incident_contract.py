"""Shared P10 behavior for in-memory and SQLite incident persistence."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

import pytest

from alpha_defense.application.communications import (
    IngestObservation,
    MessengerPayload,
    ObservationInput,
    SmsPayload,
    WebResourcePayload,
)
from alpha_defense.application.identity import IdentityUnitOfWorkPort
from alpha_defense.application.incidents import (
    AttachObservation,
    AttachObservationResult,
    CorrelationKey,
    GetIncident,
    IncidentResolutionCode,
    ResolveIncident,
)
from alpha_defense.application.ports import IncidentUnitOfWorkPort
from alpha_defense.application.shared import (
    ActorContext,
    ActorRole,
    ResourceNotFoundError,
    StaleRevisionError,
)
from alpha_defense.application.workflows import AnalyzeContact
from alpha_defense.domain.identity import DemoSession, SessionRole, SyntheticUser
from alpha_defense.domain.incidents import IncidentStatus, IncidentTimelineItemKind
from alpha_defense.domain.shared import EntityId, ExecutionMode
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from tests.contract.test_uow_contract import FrozenClock, migrate

NOW = datetime(2026, 9, 20, 14, 0, tzinfo=UTC)
DEFAULT_NAMESPACE_ID = EntityId(UUID(int=3))


class IncidentTestUnitOfWork(IncidentUnitOfWorkPort, IdentityUnitOfWorkPort, Protocol):
    pass


class IncidentTestUnitOfWorkFactory(Protocol):
    def __call__(self) -> IncidentTestUnitOfWork: ...


class SequentialIdGenerator:
    def __init__(self) -> None:
        self._value = 1_000

    def new_id(self) -> EntityId:
        self._value += 1
        return _id(self._value)


@pytest.fixture(params=["memory", "sqlite"])
def incident_uow_factory(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[IncidentTestUnitOfWorkFactory]:
    if request.param == "memory":
        memory_factory = InMemoryUnitOfWorkFactory()
        _seed_actor(memory_factory)
        yield memory_factory
        return
    database_path = tmp_path / "incident-contract.db"
    migrate(database_path)
    engine = create_sqlite_engine(database_path)
    sqlite_factory = SqlAlchemyUnitOfWorkFactory(engine)
    _seed_actor(sqlite_factory)
    yield sqlite_factory
    engine.dispose()


def _id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


def _actor(*, namespace_id: EntityId = DEFAULT_NAMESPACE_ID) -> ActorContext:
    return ActorContext(
        user_id=_id(1),
        session_id=_id(2),
        namespace_id=namespace_id,
        roles=frozenset({ActorRole.DEMO_USER}),
        consent_revision=0,
        execution_mode=ExecutionMode.MOCK,
    )


def _seed_actor(factory: IncidentTestUnitOfWorkFactory) -> None:
    user = SyntheticUser(user_id=_id(1), profile_code="demo-user", created_at=NOW)
    session = DemoSession(
        session_id=_id(2),
        user_id=user.user_id,
        manual_namespace_id=_id(3),
        roles=frozenset({SessionRole.DEMO_USER}),
        token_fingerprint="a" * 64,
        consent_revision=0,
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    with factory() as uow:
        uow.identity.add_user(user)
        uow.identity.add_session(session)
        uow.commit()


def _services(
    factory: IncidentTestUnitOfWorkFactory,
    *,
    now: datetime = NOW,
    ids: SequentialIdGenerator | None = None,
) -> tuple[AnalyzeContact, GetIncident, ResolveIncident, SequentialIdGenerator]:
    ids = ids or SequentialIdGenerator()
    ingest = IngestObservation(
        unit_of_work=factory,
        clock=FrozenClock(now),
        id_generator=ids,
    )
    attach = AttachObservation(
        unit_of_work=factory,
        clock=FrozenClock(now),
        id_generator=ids,
    )
    return (
        AnalyzeContact(
            unit_of_work=factory,
            ingest_observation=ingest,
            attach_observation=attach,
        ),
        GetIncident(unit_of_work=factory),
        ResolveIncident(
            unit_of_work=factory,
            clock=FrozenClock(NOW + timedelta(minutes=1)),
            id_generator=ids,
        ),
        ids,
    )


def _sms(
    *,
    event_id: str = "sms-1",
    conversation_id: str = "conversation-1",
    text: str = "Откройте https://shared.test/pay?step=1",
) -> ObservationInput:
    return ObservationInput(
        source_event_id=event_id,
        occurred_at=NOW - timedelta(minutes=1),
        payload=SmsPayload(
            text=text,
            sender="+7 (999) 111-22-33",
            conversation_id=conversation_id,
        ),
    )


def test_atomic_intake_is_pending_and_source_retry_does_not_advance_epoch(
    incident_uow_factory: IncidentTestUnitOfWorkFactory,
) -> None:
    workflow, _, _, _ = _services(incident_uow_factory)

    first = workflow.execute(actor=_actor(), source="manual", observation_input=_sms())
    replay = workflow.execute(actor=_actor(), source="manual", observation_input=_sms())

    assert first.created_incident
    assert first.risk_state.analysis_pending
    assert first.risk_state.ingress_risk_epoch == 1
    assert replay.duplicate_source_event
    assert replay.observation.observation_id == first.observation.observation_id
    assert replay.incident.incident_id == first.incident.incident_id
    assert replay.risk_state.ingress_risk_epoch == 1
    with incident_uow_factory() as uow:
        assert len(uow.audit.list_all()) == 2


def test_explicit_conversation_correlates_but_time_alone_does_not(
    incident_uow_factory: IncidentTestUnitOfWorkFactory,
) -> None:
    workflow, _, _, _ = _services(incident_uow_factory)
    first = workflow.execute(actor=_actor(), source="manual", observation_input=_sms())
    same_conversation = workflow.execute(
        actor=_actor(),
        source="manual",
        observation_input=ObservationInput(
            source_event_id="message-2",
            occurred_at=NOW,
            payload=MessengerPayload(
                text="Сообщение без ссылки",
                sender="UNKNOWN",
                conversation_id="conversation-1",
            ),
        ),
    )
    time_only = workflow.execute(
        actor=_actor(),
        source="manual",
        observation_input=ObservationInput(
            source_event_id="web-3",
            occurred_at=NOW,
            payload=WebResourcePayload(media_id=_id(90)),
        ),
    )

    assert same_conversation.incident.incident_id == first.incident.incident_id
    assert same_conversation.incident.context_version == 2
    assert same_conversation.incident.timeline[-1].correlation_reason is not None
    assert time_only.incident.incident_id != first.incident.incident_id
    assert time_only.risk_state.ingress_risk_epoch == 3


def test_normalized_indicator_correlates_distinct_conversations(
    incident_uow_factory: IncidentTestUnitOfWorkFactory,
) -> None:
    workflow, _, _, _ = _services(incident_uow_factory)
    first = workflow.execute(actor=_actor(), source="manual", observation_input=_sms())
    second = workflow.execute(
        actor=_actor(),
        source="manual",
        observation_input=_sms(
            event_id="sms-2",
            conversation_id="conversation-2",
            text="Повторная ссылка HTTPS://SHARED.TEST/pay?step=1#fragment",
        ),
    )

    assert second.incident.incident_id == first.incident.incident_id
    assert second.incident.timeline[-1].correlation_reason is not None
    assert second.incident.timeline[-1].correlation_reason.value == "indicator"


def test_same_correlation_key_in_another_namespace_is_independent(
    incident_uow_factory: IncidentTestUnitOfWorkFactory,
) -> None:
    workflow, _, _, _ = _services(incident_uow_factory)
    first = workflow.execute(actor=_actor(), source="scenario", observation_input=_sms())
    other = workflow.execute(
        actor=_actor(namespace_id=_id(4)),
        source="scenario",
        observation_input=_sms(),
    )

    assert other.incident.incident_id != first.incident.incident_id
    assert other.risk_state.ingress_risk_epoch == 1


class FailingAttachObservation(AttachObservation):
    def execute_in_unit_of_work(
        self,
        *,
        uow: IncidentUnitOfWorkPort,
        actor: ActorContext,
        observation_id: EntityId,
        available_keys: tuple[CorrelationKey, ...],
        accepted_at: datetime,
    ) -> AttachObservationResult:
        super().execute_in_unit_of_work(
            uow=uow,
            actor=actor,
            observation_id=observation_id,
            available_keys=available_keys,
            accepted_at=accepted_at,
        )
        raise RuntimeError("abort atomic intake")


def test_workflow_rollback_leaves_no_observation_incident_or_pending_state(
    incident_uow_factory: IncidentTestUnitOfWorkFactory,
) -> None:
    ids = SequentialIdGenerator()
    workflow = AnalyzeContact(
        unit_of_work=incident_uow_factory,
        ingest_observation=IngestObservation(
            unit_of_work=incident_uow_factory,
            clock=FrozenClock(NOW),
            id_generator=ids,
        ),
        attach_observation=FailingAttachObservation(
            unit_of_work=incident_uow_factory,
            clock=FrozenClock(NOW),
            id_generator=ids,
        ),
    )

    with pytest.raises(RuntimeError, match="abort atomic intake"):
        workflow.execute(actor=_actor(), source="manual", observation_input=_sms())

    with incident_uow_factory() as uow:
        assert (
            uow.observations.get_by_source_event(
                namespace_id=_id(3),
                source="manual",
                source_event_id="sms-1",
            )
            is None
        )
        assert (
            uow.incidents.list_for_scope(
                owner_id=_id(1),
                session_id=_id(2),
                namespace_id=_id(3),
            )
            == ()
        )
        assert uow.namespace_risk_states.get(_id(3)) is None
        assert uow.audit.list_all() == ()


def test_assessment_history_survives_new_observation(
    incident_uow_factory: IncidentTestUnitOfWorkFactory,
) -> None:
    workflow, _, _, ids = _services(incident_uow_factory)
    first = workflow.execute(actor=_actor(), source="manual", observation_input=_sms())
    with incident_uow_factory() as uow:
        incident = uow.incidents.get(first.incident.incident_id)
        assert incident is not None
        assessed_once = incident.record_assessment(
            assessment_id=_id(70),
            context_version=incident.context_version,
            assessed_at=NOW + timedelta(seconds=1),
        )
        uow.incidents.save(assessed_once, expected_revision=incident.revision)
        uow.commit()
    with incident_uow_factory() as uow:
        incident = uow.incidents.get(first.incident.incident_id)
        assert incident is not None
        assessed_twice = incident.record_assessment(
            assessment_id=_id(71),
            context_version=incident.context_version,
            assessed_at=NOW + timedelta(seconds=2),
        )
        uow.incidents.save(assessed_twice, expected_revision=incident.revision)
        uow.commit()

    later_workflow, _, _, _ = _services(
        incident_uow_factory,
        now=NOW + timedelta(seconds=3),
        ids=ids,
    )
    updated = later_workflow.execute(
        actor=_actor(),
        source="manual",
        observation_input=_sms(event_id="sms-2", text="Новое сообщение без ссылки"),
    )

    assert updated.incident.assessment_ids == (_id(70), _id(71))
    assert updated.incident.latest_assessment_id == _id(71)
    assert updated.incident.status is IncidentStatus.OPEN


def test_false_positive_resolution_preserves_pending_gate_and_owner_scope(
    incident_uow_factory: IncidentTestUnitOfWorkFactory,
) -> None:
    workflow, get, resolve, _ = _services(incident_uow_factory)
    created = workflow.execute(actor=_actor(), source="manual", observation_input=_sms())

    resolved = resolve.execute(
        actor=_actor(),
        incident_id=created.incident.incident_id,
        resolution=IncidentResolutionCode.FALSE_POSITIVE_REPORTED,
        expected_revision=created.incident.revision,
    )

    assert resolved.status is IncidentStatus.RESOLVED
    assert resolved.timeline[-1].kind is IncidentTimelineItemKind.RESOLUTION
    with incident_uow_factory() as uow:
        state = uow.namespace_risk_states.get(_id(3))
    assert state is not None
    assert state.ingress_risk_epoch == 1
    assert state.analysis_pending
    assert state.is_pending(created.observation.observation_id)
    with pytest.raises(StaleRevisionError):
        resolve.execute(
            actor=_actor(),
            incident_id=resolved.incident_id,
            resolution=IncidentResolutionCode.NO_ACTION_NEEDED,
            expected_revision=created.incident.revision,
        )
    with pytest.raises(ResourceNotFoundError):
        get.execute(actor=_actor(namespace_id=_id(4)), incident_id=resolved.incident_id)
