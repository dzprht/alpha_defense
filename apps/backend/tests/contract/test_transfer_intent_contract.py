"""P21 draft CAS and local-bank atomicity in both persistence adapters."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from alpha_defense.application.ports.transfer_intents import TransferUnitOfWorkPort
from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.domain.identity import SyntheticUser
from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import (
    CompletedOperation,
    FinancialProfile,
    IntentStatus,
    TransferIntent,
)
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from tests.contract.test_uow_contract import migrate

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


class Factory(Protocol):
    def __call__(self) -> TransferUnitOfWorkPort: ...


def _id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


def _profile() -> FinancialProfile:
    return FinancialProfile(
        profile_id=_id(10),
        owner_id=_id(1),
        namespace_id=_id(2),
        template_code="regular",
        template_version="demo-finance-v1",
        title="Учебный профиль",
        description="Только синтетическая история.",
        history_version=1,
        created_at=NOW,
        operations=(
            CompletedOperation(
                operation_id=_id(11),
                profile_id=_id(10),
                amount=Money(100_000, Currency.RUB),
                recipient_code="family",
                completed_at=NOW - timedelta(days=1),
            ),
        ),
    )


def _draft(intent_number: int = 20) -> TransferIntent:
    return TransferIntent.draft(
        intent_id=_id(intent_number),
        owner_id=_id(1),
        namespace_id=_id(2),
        profile_id=_id(10),
        amount=Money(150_000, Currency.RUB),
        recipient_code="friend",
        now=NOW,
    )


@pytest.fixture(params=["memory", "sqlite"])
def factory(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Factory]:
    if request.param == "memory":
        result = InMemoryUnitOfWorkFactory()
        with result() as uow:
            uow.identity.add_user(SyntheticUser(_id(1), "demo-user", NOW))
            uow.profiles.add(_profile())
            uow.commit()
        yield result
        return
    path = tmp_path / "transfers.db"
    migrate(path)
    engine = create_sqlite_engine(path)
    result = SqlAlchemyUnitOfWorkFactory(engine)
    with result() as uow:
        uow.identity.add_user(SyntheticUser(_id(1), "demo-user", NOW))
        uow.profiles.add(_profile())
        uow.commit()
    yield result
    engine.dispose()


def test_draft_commit_rollback_owner_and_cas(factory: Factory) -> None:
    original = _draft()
    with factory() as uow:
        uow.transfer_intents.add(original)
    with factory() as uow:
        assert uow.transfer_intents.get(original.intent_id) is None
        uow.transfer_intents.add(original)
        uow.commit()
    revised = original.revise(
        profile_id=original.profile_id,
        amount=Money(200_000, Currency.RUB),
        recipient_code="new-payee",
        now=NOW + timedelta(seconds=1),
    )
    with factory() as uow:
        assert uow.transfer_intents.list_owned(owner_id=_id(1), namespace_id=_id(2)) == (original,)
        assert uow.transfer_intents.list_owned(owner_id=_id(3), namespace_id=_id(2)) == ()
        with pytest.raises(StaleRevisionError):
            uow.transfer_intents.save(revised, expected_revision=0)
        uow.transfer_intents.save(revised, expected_revision=1)
    with factory() as uow:
        assert uow.transfer_intents.get(original.intent_id) == original
        uow.transfer_intents.save(revised, expected_revision=1)
        uow.commit()
    with factory() as uow:
        assert uow.transfer_intents.get(original.intent_id) == revised
        with pytest.raises(StaleRevisionError):
            uow.transfer_intents.save(revised, expected_revision=1)


def test_bank_result_is_local_once_and_rolls_back(factory: Factory) -> None:
    draft = _draft(30)
    checked = replace(draft, status=IntentStatus.CHECKED)
    with factory() as uow:
        uow.transfer_intents.add(checked)
        uow.commit()
    with factory() as uow:
        with pytest.raises(ValueError, match="checked"):
            uow.demo_bank.record(draft, operation_id=_id(40), recorded_at=NOW)
        first = uow.demo_bank.record(checked, operation_id=_id(40), recorded_at=NOW)
        assert first.intent_revision == 1
        assert uow.demo_bank.record(checked, operation_id=_id(41), recorded_at=NOW) == first
    with factory() as uow:
        assert uow.demo_bank.get_by_intent(checked.intent_id) is None
        committed = uow.demo_bank.record(checked, operation_id=_id(42), recorded_at=NOW)
        uow.commit()
    with factory() as uow:
        assert uow.demo_bank.get_by_intent(checked.intent_id) == committed
        assert uow.demo_bank.record(checked, operation_id=_id(43), recorded_at=NOW) == committed
        with pytest.raises(StaleRevisionError):
            uow.demo_bank.record(
                replace(checked, revision=2), operation_id=_id(44), recorded_at=NOW
            )


def test_sqlite_bank_result_survives_restart_and_cannot_be_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "bank-restart.db"
    migrate(path)
    engine = create_sqlite_engine(path)
    factory = SqlAlchemyUnitOfWorkFactory(engine)
    checked = replace(_draft(50), status=IntentStatus.CHECKED)
    with factory() as uow:
        uow.identity.add_user(SyntheticUser(_id(1), "demo-user", NOW))
        uow.profiles.add(_profile())
        uow.transfer_intents.add(checked)
        result = uow.demo_bank.record(checked, operation_id=_id(51), recorded_at=NOW)
        uow.commit()
    engine.dispose()
    reopened = create_sqlite_engine(path)
    with SqlAlchemyUnitOfWorkFactory(reopened)() as uow:
        assert uow.demo_bank.get_by_intent(checked.intent_id) == result
        assert uow.demo_bank.record(checked, operation_id=_id(52), recorded_at=NOW) == result
    with pytest.raises(SQLAlchemyError), reopened.begin() as connection:
        connection.execute(sa.text("UPDATE demo_bank_results SET amount_minor = 1"))
    with pytest.raises(SQLAlchemyError), reopened.begin() as connection:
        connection.execute(sa.text("DELETE FROM demo_bank_results"))
    reopened.dispose()
