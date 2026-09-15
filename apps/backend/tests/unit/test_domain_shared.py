"""Unit tests for shared domain value objects."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from alpha_defense.domain.shared import (
    MAX_AMOUNT_MINOR,
    Currency,
    EntityId,
    ExecutionMode,
    Money,
    Provenance,
    Severity,
)


def test_entity_id_parses_and_renders_canonical_uuid() -> None:
    value = uuid4()

    entity_id = EntityId.from_string(str(value).upper())

    assert entity_id.value == value
    assert str(entity_id) == str(value)


@pytest.mark.parametrize("raw_value", ["", "not-a-uuid", " 00000000-0000-0000-0000-000000000000 "])
def test_entity_id_rejects_invalid_strings(raw_value: str) -> None:
    with pytest.raises(ValueError, match="valid UUID"):
        EntityId.from_string(raw_value)


def test_entity_id_rejects_non_uuid_value() -> None:
    with pytest.raises(TypeError, match="must be a UUID"):
        EntityId("not-a-uuid")  # type: ignore[arg-type]


def test_money_accepts_positive_integer_minor_units() -> None:
    money = Money(amount_minor=1_500_000, currency=Currency.RUB)

    assert money.amount_minor == 1_500_000
    assert money.currency is Currency.RUB
    assert Money(amount_minor=MAX_AMOUNT_MINOR, currency=Currency.RUB).amount_minor == 100_000_000


@pytest.mark.parametrize("amount_minor", [True, 1.0, Decimal("1"), "1"])
def test_money_rejects_fractional_or_non_integer_amounts(amount_minor: object) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        Money(amount_minor=amount_minor, currency=Currency.RUB)  # type: ignore[arg-type]


@pytest.mark.parametrize("amount_minor", [0, -1, MAX_AMOUNT_MINOR + 1])
def test_money_rejects_out_of_range_amounts(amount_minor: int) -> None:
    with pytest.raises(ValueError, match="between"):
        Money(amount_minor=amount_minor, currency=Currency.RUB)


def test_money_rejects_unsupported_currency_representation() -> None:
    with pytest.raises(TypeError, match="supported Currency"):
        Money(amount_minor=100, currency="USD")  # type: ignore[arg-type]


def test_stable_domain_enums_match_contract_values() -> None:
    assert [severity.value for severity in Severity] == [
        "low",
        "medium",
        "high",
        "critical",
        "unknown",
    ]
    assert [mode.value for mode in ExecutionMode] == ["mock", "live"]


def test_provenance_is_immutable_and_versioned() -> None:
    provenance = Provenance(
        execution_mode=ExecutionMode.MOCK,
        provider="fixture-analyzer",
        provider_version="1.0.0",
        data_version="demo-v1",
    )

    assert provenance.execution_mode is ExecutionMode.MOCK
    with pytest.raises(ValueError, match="non-empty and trimmed"):
        Provenance(ExecutionMode.MOCK, " fixture ", "1.0.0", "demo-v1")


def test_entity_id_accepts_uuid_constructor_value() -> None:
    nil_uuid = UUID("00000000-0000-0000-0000-000000000000")

    assert EntityId(nil_uuid).value == nil_uuid
