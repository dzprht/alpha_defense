"""P19 behavior evidence must not mistake sparse or future history for safety."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import (
    CompletedOperation,
    FinancialProfile,
    HistoryStatus,
    assess_history,
)

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


def _id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


def _operation(number: int, *, days_ago: int, amount_minor: int = 100_000) -> CompletedOperation:
    return CompletedOperation(
        operation_id=_id(number),
        profile_id=_id(1),
        amount=Money(amount_minor, Currency.RUB),
        recipient_code="family",
        completed_at=NOW - timedelta(days=days_ago),
    )


def _profile(operations: tuple[CompletedOperation, ...]) -> FinancialProfile:
    return FinancialProfile(
        profile_id=_id(1),
        owner_id=_id(2),
        namespace_id=_id(3),
        template_code="regular",
        template_version="demo-finance-v1",
        title="Учебный профиль",
        description="Только синтетическая история.",
        history_version=1,
        created_at=NOW,
        operations=tuple(
            sorted(operations, key=lambda item: (item.completed_at, str(item.operation_id)))
        ),
    )


def test_new_recipient_and_large_amount_are_descriptive_features() -> None:
    profile = _profile(tuple(_operation(index, days_ago=index) for index in range(10, 22)))
    unusual = assess_history(
        profile, amount=Money(400_000, Currency.RUB), recipient_code="new-payee", as_of=NOW
    )
    familiar = assess_history(
        profile, amount=Money(100_000, Currency.RUB), recipient_code="family", as_of=NOW
    )
    assert unusual.status is HistoryStatus.COMPLETE
    assert unusual.sample_size == 12
    assert unusual.median_amount_minor_x2 == 200_000
    assert unusual.recipient_is_new and unusual.amount_is_outlier
    assert familiar.recipient_is_new is False and familiar.amount_is_outlier is False


def test_sparse_history_and_current_or_future_operation_remain_insufficient() -> None:
    profile = _profile(
        (
            *(_operation(index, days_ago=index) for index in range(1, 10)),
            _operation(20, days_ago=0),
            _operation(21, days_ago=-1),
            _operation(22, days_ago=91),
        )
    )
    result = assess_history(
        profile, amount=Money(400_000, Currency.RUB), recipient_code="new-payee", as_of=NOW
    )
    assert result.status is HistoryStatus.INSUFFICIENT_DATA
    assert result.sample_size == 9
    assert result.recipient_is_new is None
    assert result.amount_is_outlier is None
    assert result.median_amount_minor_x2 is None


def test_even_median_uses_integer_arithmetic_at_outlier_threshold() -> None:
    profile = _profile(
        tuple(
            _operation(
                index,
                days_ago=index,
                amount_minor=100_000 if index <= 5 else 101_000,
            )
            for index in range(1, 11)
        )
    )
    at_boundary = assess_history(
        profile, amount=Money(301_500, Currency.RUB), recipient_code="family", as_of=NOW
    )
    just_above = assess_history(
        profile, amount=Money(301_501, Currency.RUB), recipient_code="family", as_of=NOW
    )
    assert at_boundary.median_amount_minor_x2 == 201_000
    assert at_boundary.amount_is_outlier is False
    assert just_above.amount_is_outlier is True


def test_exact_90_day_boundary_is_included_and_history_only_appends() -> None:
    profile = _profile(
        (
            *(_operation(index, days_ago=index) for index in range(1, 10)),
            _operation(20, days_ago=90),
        )
    )
    result = assess_history(
        profile, amount=Money(100_000, Currency.RUB), recipient_code="family", as_of=NOW
    )
    assert result.sample_size == 10
    assert result.status is HistoryStatus.COMPLETE

    next_operation = _operation(100, days_ago=-1)
    grown = profile.append_completed(next_operation)
    profile.assert_successor(grown)
    assert grown.history_version == 2
    assert grown.operations[:-1] == profile.operations
    with pytest.raises(ValueError, match="older history"):
        profile.append_completed(_operation(101, days_ago=5))
    with pytest.raises(ValueError, match="only grow"):
        profile.assert_successor(
            FinancialProfile(
                profile_id=profile.profile_id,
                owner_id=profile.owner_id,
                namespace_id=profile.namespace_id,
                template_code=profile.template_code,
                template_version=profile.template_version,
                title=profile.title,
                description=profile.description,
                history_version=2,
                created_at=profile.created_at,
                operations=(next_operation,),
            )
        )
