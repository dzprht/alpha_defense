"""The same append-only owner profile behavior in memory and SQLite."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

import pytest

from alpha_defense.application.ports.financial_profiles import ProfileUnitOfWorkPort
from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.domain.identity import SyntheticUser
from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import CompletedOperation, FinancialProfile
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from tests.contract.test_uow_contract import migrate

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


class ProfileFactory(Protocol):
    def __call__(self) -> ProfileUnitOfWorkPort: ...


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
                completed_at=NOW - timedelta(days=10),
            ),
        ),
    )


@pytest.fixture(params=["memory", "sqlite"])
def profile_factory(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[ProfileFactory]:
    if request.param == "memory":
        factory = InMemoryUnitOfWorkFactory()
        with factory() as uow:
            uow.identity.add_user(SyntheticUser(_id(1), "demo-user", NOW))
            uow.commit()
        yield factory
        return
    path = tmp_path / "profiles.db"
    migrate(path)
    engine = create_sqlite_engine(path)
    factory = SqlAlchemyUnitOfWorkFactory(engine)
    with factory() as uow:
        uow.identity.add_user(SyntheticUser(_id(1), "demo-user", NOW))
        uow.commit()
    yield factory
    engine.dispose()


def test_profile_repository_commit_rollback_owner_and_append(
    profile_factory: ProfileFactory,
) -> None:
    original = _profile()
    with profile_factory() as uow:
        uow.profiles.add(original)
        assert uow.profiles.get(original.profile_id) == original
    with profile_factory() as uow:
        assert uow.profiles.get(original.profile_id) is None
        uow.profiles.add(original)
        uow.commit()
    with profile_factory() as uow:
        assert (
            uow.profiles.get_by_template(
                owner_id=_id(1), namespace_id=_id(2), template_code="regular"
            )
            == original
        )
        assert uow.profiles.list_owned(owner_id=_id(1), namespace_id=_id(2)) == (original,)
        assert uow.profiles.list_owned(owner_id=_id(3), namespace_id=_id(2)) == ()
        assert uow.profiles.list_owned(owner_id=_id(1), namespace_id=_id(3)) == ()
    appended = original.append_completed(
        CompletedOperation(
            operation_id=_id(12),
            profile_id=original.profile_id,
            amount=Money(150_000, Currency.RUB),
            recipient_code="utilities",
            completed_at=NOW,
        )
    )
    with profile_factory() as uow:
        with pytest.raises(StaleRevisionError):
            uow.profiles.append_completed(appended, expected_version=0)
        uow.profiles.append_completed(appended, expected_version=1)
    with profile_factory() as uow:
        assert uow.profiles.get(original.profile_id) == original
        uow.profiles.append_completed(appended, expected_version=1)
        uow.commit()
    with profile_factory() as uow:
        assert uow.profiles.get(original.profile_id) == appended
        with pytest.raises(StaleRevisionError):
            uow.profiles.append_completed(appended, expected_version=1)
