"""P22 check persistence and intent transition in both transactional adapters."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

import pytest

from alpha_defense.application.ports.transfer_intents import TransferUnitOfWorkPort
from alpha_defense.domain.identity import SyntheticUser
from alpha_defense.domain.shared import Currency, EntityId, Money, Severity
from alpha_defense.domain.transfers import (
    CheckCompleteness,
    ContactEvidenceStatus,
    FinancialProfile,
    HistoryStatus,
    IntentStatus,
    RecipientLookupStatus,
    TransferCheck,
    TransferDecision,
    TransferIntent,
)
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from tests.contract.test_uow_contract import migrate

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


def _id(value: int) -> EntityId:
    return EntityId(UUID(int=value))


class Factory(Protocol):
    def __call__(self) -> TransferUnitOfWorkPort: ...


@pytest.fixture(params=["memory", "sqlite"])
def factory(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Factory]:
    if request.param == "memory":
        result = InMemoryUnitOfWorkFactory()
        engine = None
    else:
        path = tmp_path / "transfer-check-contract.db"
        migrate(path)
        engine = create_sqlite_engine(path)
        result = SqlAlchemyUnitOfWorkFactory(engine)
    profile = FinancialProfile(
        profile_id=_id(3),
        owner_id=_id(1),
        namespace_id=_id(2),
        template_code="regular",
        template_version="demo-finance-v1",
        title="Учебный профиль",
        description="Синтетическая история.",
        history_version=1,
        created_at=NOW,
        operations=(),
    )
    intent = TransferIntent.draft(
        intent_id=_id(4),
        owner_id=_id(1),
        namespace_id=_id(2),
        profile_id=profile.profile_id,
        amount=Money(100_000, Currency.RUB),
        recipient_code="family",
        now=NOW,
    )
    with result() as uow:
        uow.identity.add_user(SyntheticUser(_id(1), "demo-user", NOW))
        uow.profiles.add(profile)
        uow.transfer_intents.add(intent)
        uow.commit()
    yield result
    if engine is not None:
        engine.dispose()


def _check(intent: TransferIntent) -> TransferCheck:
    return TransferCheck(
        check_id=_id(5),
        intent_id=intent.intent_id,
        owner_id=intent.owner_id,
        namespace_id=intent.namespace_id,
        intent_revision=intent.revision,
        intent_fingerprint=intent.fingerprint,
        profile_id=intent.profile_id,
        history_version=1,
        consent_revision=1,
        ingress_epoch=0,
        linked_incident_id=None,
        context_version=None,
        contact_assessment_id=None,
        model_version=None,
        policy_version="transfer-risk-v1",
        catalog_policy_version="demo-risk-v2:abc",
        registry_snapshot_id=None,
        registry_version=None,
        registry_valid_until=None,
        behavior_status=HistoryStatus.COMPLETE,
        sample_size=12,
        recipient_is_new=False,
        amount_is_outlier=False,
        recipient_lookup=RecipientLookupStatus.NO_MATCH,
        contact_status=ContactEvidenceStatus.NOT_SELECTED,
        severity=Severity.LOW,
        score=0,
        completeness=CheckCompleteness.COMPLETE,
        decision=TransferDecision.ALLOW,
        signal_codes=(),
        reason_codes=("decision_allow",),
        checked_at=NOW + timedelta(seconds=1),
        expires_at=NOW + timedelta(seconds=121),
    )


def test_check_and_status_rollback_and_commit_together(factory: Factory) -> None:
    with factory() as uow:
        intent = uow.transfer_intents.get(_id(4))
        assert intent is not None
        checked = intent.mark_checked(now=NOW + timedelta(seconds=1))
        check = _check(intent)
        uow.transfer_intents.mark_checked(checked, expected_revision=1)
        uow.transfer_checks.add(check)
        # No commit: both must roll back.
    with factory() as uow:
        assert uow.transfer_intents.get(_id(4)) == intent
        assert uow.transfer_checks.get(check.check_id) is None
        uow.transfer_intents.mark_checked(checked, expected_revision=1)
        uow.transfer_checks.add(check)
        uow.commit()
    with factory() as uow:
        assert uow.transfer_intents.get(intent.intent_id) == checked
        assert uow.transfer_checks.get(check.check_id) == check
        assert uow.transfer_checks.get_latest_for_intent(intent.intent_id) == check
        assert uow.transfer_checks.list_for_intent(intent.intent_id) == (check,)
        assert uow.transfer_checks.list_for_intent(_id(99)) == ()
        assert checked.status is IntentStatus.CHECKED
