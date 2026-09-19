"""One identity-service contract exercised against both persistence adapters."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from alpha_defense.application.identity import IdentityService, IdentityUnitOfWorkFactory
from alpha_defense.application.shared import StaleRevisionError, ValidationError
from alpha_defense.domain.identity import ConsentScope, ConsentStatus
from alpha_defense.domain.shared import ExecutionMode
from alpha_defense.infrastructure.identity.mock import HmacSecurityTokens, SyntheticIdentityProvider
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from alpha_defense.infrastructure.runtime import UuidGenerator
from tests.contract.test_uow_contract import FrozenClock, migrate


@pytest.fixture(params=["memory", "sqlite"])
def identity_uow_factory(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[IdentityUnitOfWorkFactory]:
    if request.param == "memory":
        yield InMemoryUnitOfWorkFactory()
        return
    database_path = tmp_path / "identity-contract.db"
    migrate(database_path)
    engine = create_sqlite_engine(database_path)
    yield SqlAlchemyUnitOfWorkFactory(engine)
    engine.dispose()


def make_service(factory: IdentityUnitOfWorkFactory) -> IdentityService:
    return IdentityService(
        unit_of_work=factory,
        clock=FrozenClock(),
        id_generator=UuidGenerator(),
        provider=SyntheticIdentityProvider(),
        tokens=HmacSecurityTokens("identity-contract-secret-with-32-characters"),
        execution_mode=ExecutionMode.MOCK,
    )


def test_session_replay_and_revisioned_consents(
    identity_uow_factory: IdentityUnitOfWorkFactory,
) -> None:
    service = make_service(identity_uow_factory)
    bootstrap = service.bootstrap_session(session_token=None, pre_session_token=None)
    assert bootstrap.pre_session_token is not None

    created = service.start_session(
        pre_session_token=bootstrap.pre_session_token,
        idempotency_key="start-one",
        profile_code="demo-user",
    )
    replayed = service.start_session(
        pre_session_token=bootstrap.pre_session_token,
        idempotency_key="start-one",
        profile_code="demo-user",
    )
    actor = service.resolve_actor(created.session_token)

    granted = service.update_consent(
        actor=actor,
        idempotency_key="grant-research",
        scope=ConsentScope.PARTICIPATE_IN_RESEARCH,
        status=ConsentStatus.GRANTED,
        expected_revision=0,
    )
    repeated_grant = service.update_consent(
        actor=service.resolve_actor(created.session_token),
        idempotency_key="grant-research",
        scope=ConsentScope.PARTICIPATE_IN_RESEARCH,
        status=ConsentStatus.GRANTED,
        expected_revision=0,
    )

    assert replayed.replayed
    assert replayed.view.session_id == created.view.session_id
    assert replayed.session_token == created.session_token
    assert created.view.roles[0].value == "demo_user"
    assert len(created.view.consents) == len(ConsentScope)
    assert all(item.status is ConsentStatus.REVOKED for item in created.view.consents)
    assert granted == repeated_grant
    assert granted.revision == 1
    with pytest.raises(StaleRevisionError):
        service.update_consent(
            actor=service.resolve_actor(created.session_token),
            idempotency_key="stale-update",
            scope=ConsentScope.SEND_NOTIFICATIONS,
            status=ConsentStatus.GRANTED,
            expected_revision=0,
        )

    with identity_uow_factory() as uow:
        stored = uow.identity.get_session(created.view.session_id)
        consents = uow.identity.list_consents(created.view.user_id)
        audits = uow.audit.list_all()
    assert stored is not None
    assert stored.consent_revision == 1
    assert len(consents) == len(ConsentScope)
    assert {record.event.event_type for record in audits} == {
        "session.started",
        "consent.changed",
    }


def test_failed_synthetic_auth_rolls_back_the_command_reservation(
    identity_uow_factory: IdentityUnitOfWorkFactory,
) -> None:
    service = make_service(identity_uow_factory)
    bootstrap = service.bootstrap_session(session_token=None, pre_session_token=None)
    assert bootstrap.pre_session_token is not None

    with pytest.raises(ValidationError):
        service.start_session(
            pre_session_token=bootstrap.pre_session_token,
            idempotency_key="reusable-after-validation",
            profile_code="unknown-profile",
        )

    created = service.start_session(
        pre_session_token=bootstrap.pre_session_token,
        idempotency_key="reusable-after-validation",
        profile_code="demo-senior",
    )

    assert created.view.roles[0].value == "demo_user"
