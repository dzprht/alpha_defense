"""Common P09 behavior for in-memory and SQLite observation persistence."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

import pytest

from alpha_defense.application.communications import (
    CallTranscriptPayload,
    GetObservation,
    IngestObservation,
    MessengerPayload,
    ObservationInput,
    SmsPayload,
    TranscriptSegment,
    WebResourcePayload,
)
from alpha_defense.application.identity import IdentityUnitOfWorkPort
from alpha_defense.application.ports import CommunicationsUnitOfWorkPort
from alpha_defense.application.shared import (
    ActorContext,
    ActorRole,
    ResourceNotFoundError,
    ValidationError,
)
from alpha_defense.domain.communications import (
    CommunicationIndicatorType,
    NormalizationStatus,
    StoredObservation,
)
from alpha_defense.domain.identity import DemoSession, SessionRole, SyntheticUser
from alpha_defense.domain.shared import EntityId, ExecutionMode
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from tests.contract.test_uow_contract import FrozenClock, migrate

NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


class ObservationTestUnitOfWork(CommunicationsUnitOfWorkPort, IdentityUnitOfWorkPort, Protocol):
    pass


class ObservationTestUnitOfWorkFactory(Protocol):
    def __call__(self) -> ObservationTestUnitOfWork: ...


class SequentialIdGenerator:
    def __init__(self) -> None:
        self._value = 100

    def new_id(self) -> EntityId:
        self._value += 1
        return EntityId(UUID(int=self._value))


@pytest.fixture(params=["memory", "sqlite"])
def observation_uow_factory(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[ObservationTestUnitOfWorkFactory]:
    if request.param == "memory":
        memory_factory = InMemoryUnitOfWorkFactory()
        _seed_actor(memory_factory)
        yield memory_factory
        return
    database_path = tmp_path / "communications-contract.db"
    migrate(database_path)
    engine = create_sqlite_engine(database_path)
    sqlite_factory = SqlAlchemyUnitOfWorkFactory(engine)
    _seed_actor(sqlite_factory)
    yield sqlite_factory
    engine.dispose()


def _id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


DEFAULT_NAMESPACE_ID = _id(3)


def _actor(*, namespace_id: EntityId = DEFAULT_NAMESPACE_ID) -> ActorContext:
    return ActorContext(
        user_id=_id(1),
        session_id=_id(2),
        namespace_id=namespace_id,
        roles=frozenset({ActorRole.DEMO_USER}),
        consent_revision=0,
        execution_mode=ExecutionMode.MOCK,
    )


def _seed_actor(factory: ObservationTestUnitOfWorkFactory) -> None:
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
    factory: ObservationTestUnitOfWorkFactory,
) -> tuple[IngestObservation, GetObservation]:
    return (
        IngestObservation(
            unit_of_work=factory,
            clock=FrozenClock(NOW),
            id_generator=SequentialIdGenerator(),
        ),
        GetObservation(unit_of_work=factory),
    )


def _sms(*, event_id: str = "sms-event-1", text: str | None = None) -> ObservationInput:
    raw_text = text or (
        "  Срочно откройте HTTPS://Example.TEST/Pay/Step?order=42&next=yes#private  "
    )
    return ObservationInput(
        source_event_id=event_id,
        occurred_at=NOW - timedelta(minutes=1),
        payload=SmsPayload(
            text=raw_text,
            sender="ALFA-DEMO",
            conversation_id="conversation-1",
        ),
    )


def test_raw_content_and_normalized_indicators_remain_distinct(
    observation_uow_factory: ObservationTestUnitOfWorkFactory,
) -> None:
    ingest, get = _services(observation_uow_factory)
    raw = _sms()
    assert isinstance(raw.payload, SmsPayload)

    result = ingest.execute(actor=_actor(), source="manual", observation_input=raw)
    restored = get.execute(actor=_actor(), observation_id=result.observation.observation_id)

    assert not result.duplicate
    assert isinstance(restored.payload, SmsPayload)
    assert restored.payload.text == raw.payload.text
    phone = restored.normalized_indicators[0]
    assert phone.indicator_type is CommunicationIndicatorType.PHONE
    assert phone.status is NormalizationStatus.INVALID
    assert phone.normalized_value is None
    assert [item.normalized_value for item in restored.normalized_indicators[1:]] == [
        "https://example.test/Pay/Step?order=42&next=yes",
        "example.test",
    ]


def test_source_event_repeat_is_deduplicated_but_other_namespace_is_independent(
    observation_uow_factory: ObservationTestUnitOfWorkFactory,
) -> None:
    ingest, _ = _services(observation_uow_factory)
    observation_input = _sms()

    first = ingest.execute(actor=_actor(), source="scenario", observation_input=observation_input)
    repeated = ingest.execute(
        actor=_actor(), source="scenario", observation_input=observation_input
    )
    with pytest.raises(ValidationError) as captured:
        ingest.execute(
            actor=_actor(),
            source="scenario",
            observation_input=_sms(text="Измененное содержание"),
        )
    other_run = ingest.execute(
        actor=_actor(namespace_id=_id(4)),
        source="scenario",
        observation_input=observation_input,
    )

    assert repeated.duplicate
    assert repeated.observation.observation_id == first.observation.observation_id
    assert captured.value.field_errors[0].code == "source_event_conflict"
    assert other_run.observation.observation_id != first.observation.observation_id
    with observation_uow_factory() as uow:
        audits = tuple(uow.audit.list_all())
    assert [record.event.event_type for record in audits] == [
        "observation.received",
        "observation.received",
    ]
    assert all("text" not in record.event.payload for record in audits)


def test_all_payload_variants_and_call_sequence_survive_storage(
    observation_uow_factory: ObservationTestUnitOfWorkFactory,
) -> None:
    ingest, get = _services(observation_uow_factory)
    media_id = _id(50)
    inputs = (
        ObservationInput(
            source_event_id="messenger-1",
            occurred_at=NOW,
            payload=MessengerPayload(
                text="Сообщение в чате",
                sender="+7 (999) 123-45-67",
                conversation_id="chat-1",
            ),
        ),
        ObservationInput(
            source_event_id="call-1-part-2",
            occurred_at=NOW,
            payload=CallTranscriptPayload(
                transcript="Перейдите на https://voice.test/check?step=2",
                phone="invalid-phone",
                call_id="call-1",
                sequence=2,
                segments=(
                    TranscriptSegment(sequence=4, text="Перейдите", start_ms=0, end_ms=500),
                    TranscriptSegment(sequence=5, text="по ссылке", start_ms=500, end_ms=900),
                ),
            ),
        ),
        ObservationInput(
            source_event_id="web-1",
            occurred_at=NOW,
            payload=WebResourcePayload(
                url="https://resource.test/a/b?token=synthetic#fragment",
                media_id=media_id,
            ),
        ),
    )

    results = [
        ingest.execute(actor=_actor(), source="manual", observation_input=item) for item in inputs
    ]
    restored = [
        get.execute(actor=_actor(), observation_id=item.observation.observation_id)
        for item in results
    ]

    assert isinstance(restored[0].payload, MessengerPayload)
    assert restored[0].normalized_indicators[0].normalized_value == "+79991234567"
    assert isinstance(restored[1].payload, CallTranscriptPayload)
    assert restored[1].payload.sequence == 2
    assert [segment.sequence for segment in restored[1].payload.segments] == [4, 5]
    assert restored[1].normalized_indicators[0].status is NormalizationStatus.INVALID
    assert isinstance(restored[2].payload, WebResourcePayload)
    assert restored[2].media_refs == (media_id,)
    assert restored[2].normalized_indicators[0].normalized_value == (
        "https://resource.test/a/b?token=synthetic"
    )


def test_future_timestamp_and_invalid_resource_url_are_typed_validation_errors(
    observation_uow_factory: ObservationTestUnitOfWorkFactory,
) -> None:
    ingest, _ = _services(observation_uow_factory)
    future = replace(_sms(), occurred_at=NOW + timedelta(minutes=6))
    invalid_url = ObservationInput(
        source_event_id="web-invalid",
        occurred_at=NOW,
        payload=WebResourcePayload(url="ftp://resource.test/path"),
    )

    with pytest.raises(ValidationError) as future_error:
        ingest.execute(actor=_actor(), source="manual", observation_input=future)
    with pytest.raises(ValidationError) as url_error:
        ingest.execute(actor=_actor(), source="manual", observation_input=invalid_url)

    assert future_error.value.field_errors[0].code == "future_timestamp"
    assert url_error.value.field_errors[0].code == "invalid_url"


def test_observation_content_and_audit_roll_back_together(
    observation_uow_factory: ObservationTestUnitOfWorkFactory,
) -> None:
    ingest, _ = _services(observation_uow_factory)
    first = ingest.execute(actor=_actor(), source="manual", observation_input=_sms())
    rollback_id = _id(900)

    with pytest.raises(RuntimeError, match="abort observation"), observation_uow_factory() as uow:
        original = uow.observations.get(first.observation.observation_id)
        assert original is not None
        content_ref = _id(901)
        candidate = StoredObservation(
            observation=replace(
                original.observation,
                observation_id=rollback_id,
                content_ref=content_ref,
                source_event_id="rollback-event",
            ),
            content=replace(
                original.content,
                observation_id=rollback_id,
                content_ref=content_ref,
            ),
        )
        uow.observations.add(candidate)
        raise RuntimeError("abort observation")

    with observation_uow_factory() as uow:
        assert uow.observations.get(rollback_id) is None


def test_get_hides_observation_from_another_namespace(
    observation_uow_factory: ObservationTestUnitOfWorkFactory,
) -> None:
    ingest, get = _services(observation_uow_factory)
    created = ingest.execute(actor=_actor(), source="manual", observation_input=_sms())

    with pytest.raises(ResourceNotFoundError):
        get.execute(
            actor=_actor(namespace_id=_id(44)),
            observation_id=created.observation.observation_id,
        )
