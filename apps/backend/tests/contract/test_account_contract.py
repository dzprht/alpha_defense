"""Account lifecycle and ownership invariants across both persistence adapters."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from alpha_defense.application.identity import AccountService, IdentityService
from alpha_defense.application.identity.ports import IdentityUnitOfWorkFactory
from alpha_defense.application.shared import (
    InvalidCredentialsError,
    RateLimitedError,
    SessionRequiredError,
    StaleRevisionError,
    ValidationError,
)
from alpha_defense.domain.identity import ConsentScope, ConsentStatus
from alpha_defense.domain.shared import ExecutionMode
from alpha_defense.infrastructure.identity.credentials import Argon2Credentials
from alpha_defense.infrastructure.identity.mock import HmacSecurityTokens, SyntheticIdentityProvider
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from alpha_defense.infrastructure.runtime import UuidGenerator
from tests.contract.test_uow_contract import FrozenClock, migrate

SECRET = "account-contract-secret-at-least-32-characters"
PASSWORD = "synthetic-password-123"


@pytest.fixture(params=["memory", "sqlite"])
def factory(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[IdentityUnitOfWorkFactory]:
    if request.param == "memory":
        yield InMemoryUnitOfWorkFactory()
        return
    database_path = tmp_path / "account-contract.db"
    migrate(database_path)
    engine = create_sqlite_engine(database_path)
    yield SqlAlchemyUnitOfWorkFactory(engine)
    engine.dispose()


def services(factory: IdentityUnitOfWorkFactory) -> tuple[IdentityService, AccountService]:
    clock = FrozenClock()
    ids = UuidGenerator()
    tokens = HmacSecurityTokens(SECRET)
    return (
        IdentityService(
            factory, clock, ids, SyntheticIdentityProvider(), tokens, ExecutionMode.MOCK
        ),
        AccountService(factory, clock, ids, Argon2Credentials(), tokens, ExecutionMode.MOCK),
    )


def pre_token(identity: IdentityService) -> str:
    bootstrap = identity.bootstrap_session(session_token=None, pre_session_token=None)
    assert bootstrap.pre_session_token is not None
    return bootstrap.pre_session_token


def test_account_is_stable_across_sessions_and_demo_is_not_adopted(
    factory: IdentityUnitOfWorkFactory,
) -> None:
    identity, accounts = services(factory)
    demo = identity.start_session(
        pre_session_token=pre_token(identity),
        idempotency_key="demo",
        profile_code="demo-user",
    )
    token = pre_token(identity)
    first = accounts.register(
        pre_session_token=token,
        idempotency_key="register",
        login="  Alice  ",
        password=PASSWORD,
    )
    repeated = accounts.register(
        pre_session_token=token,
        idempotency_key="register",
        login="alice",
        password=PASSWORD,
    )
    second = accounts.login(
        pre_session_token=pre_token(identity),
        idempotency_key="login",
        login="ALICE",
        password=PASSWORD,
    )
    other = accounts.register(
        pre_session_token=pre_token(identity),
        idempotency_key="other",
        login="bobby",
        password=PASSWORD,
    )

    assert repeated.replayed and repeated.view.session_id == first.view.session_id
    assert first.view.user_id == second.view.user_id
    assert first.view.namespace_id == second.view.namespace_id
    assert first.view.session_id != second.view.session_id
    assert first.view.namespace_id != demo.view.namespace_id
    assert first.view.user_id != demo.view.user_id
    assert other.view.namespace_id != first.view.namespace_id
    assert other.view.user_id != first.view.user_id

    accounts.logout(session_token=demo.session_token, idempotency_key="leave-demo")
    with pytest.raises(SessionRequiredError):
        identity.resolve_actor(demo.session_token)

    granted = identity.update_consent(
        actor=identity.resolve_actor(first.session_token),
        idempotency_key="grant",
        scope=ConsentScope.ANALYZE_COMMUNICATIONS,
        status=ConsentStatus.GRANTED,
        expected_revision=0,
    )
    assert granted.revision == 1
    assert identity.resolve_actor(second.session_token).consent_revision == 1
    assert (
        identity.bootstrap_session(
            session_token=second.session_token,
            pre_session_token=None,
        )
        .view.consents[0]
        .status
        is ConsentStatus.GRANTED
    )
    with pytest.raises(StaleRevisionError):
        identity.update_consent(
            actor=identity.resolve_actor(second.session_token),
            idempotency_key="stale",
            scope=ConsentScope.ANALYZE_RESOURCES,
            status=ConsentStatus.GRANTED,
            expected_revision=0,
        )
    assert identity.resolve_actor(other.session_token).consent_revision == 0

    accounts.logout(session_token=first.session_token, idempotency_key="logout")
    accounts.logout(session_token=first.session_token, idempotency_key="logout")
    with pytest.raises(SessionRequiredError):
        identity.resolve_actor(first.session_token)
    assert identity.resolve_actor(second.session_token).user_id == first.view.user_id


def test_invalid_login_throttle_and_registration_rollback(
    factory: IdentityUnitOfWorkFactory,
) -> None:
    identity, accounts = services(factory)
    accounts.register(
        pre_session_token=pre_token(identity),
        idempotency_key="register",
        login="alice",
        password=PASSWORD,
    )
    retry_token = pre_token(identity)
    with pytest.raises(ValidationError):
        accounts.register(
            pre_session_token=retry_token,
            idempotency_key="duplicate",
            login="ALICE",
            password=PASSWORD,
        )
    # The failed transaction did not consume its pre-session or reserve its key.
    accounts.register(
        pre_session_token=retry_token,
        idempotency_key="new-name",
        login="carol",
        password=PASSWORD,
    )
    with pytest.raises(InvalidCredentialsError, match="Неверный логин или пароль"):
        accounts.login(
            pre_session_token=pre_token(identity),
            idempotency_key="unknown-login",
            login="nobody",
            password=PASSWORD,
        )
    for index in range(5):
        token = pre_token(identity)
        with pytest.raises(InvalidCredentialsError):
            accounts.login(
                pre_session_token=token,
                idempotency_key=f"bad-{index}",
                login="alice",
                password="incorrect-pass-123",
            )
        if index == 0:
            with pytest.raises(InvalidCredentialsError):
                accounts.login(
                    pre_session_token=token,
                    idempotency_key="bad-0",
                    login="alice",
                    password="incorrect-pass-123",
                )
    with pytest.raises(RateLimitedError):
        accounts.login(
            pre_session_token=pre_token(identity),
            idempotency_key="blocked",
            login="alice",
            password=PASSWORD,
        )
