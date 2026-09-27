"""P21 fingerprint, revision, and local-bank result invariants."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import (
    DemoBankResult,
    DemoBankStatus,
    IntentStatus,
    TransferIntent,
    transfer_fingerprint,
)

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


def _id(value: int) -> EntityId:
    return EntityId(UUID(int=value))


def _draft() -> TransferIntent:
    return TransferIntent.draft(
        intent_id=_id(1),
        owner_id=_id(2),
        namespace_id=_id(3),
        profile_id=_id(4),
        amount=Money(120_000, Currency.RUB),
        recipient_code="family",
        now=NOW,
    )


def test_material_changes_advance_revision_and_fingerprint() -> None:
    first = _draft()
    assert first.revision == 1
    assert first.status is IntentStatus.DRAFT
    assert (
        first.revise(
            profile_id=first.profile_id,
            amount=first.amount,
            recipient_code=first.recipient_code,
            now=NOW,
        )
        == first
    )
    amount_changed = first.revise(
        profile_id=first.profile_id,
        amount=Money(130_000, Currency.RUB),
        recipient_code=first.recipient_code,
        now=NOW + timedelta(seconds=1),
    )
    first.assert_successor(amount_changed)
    assert amount_changed.revision == 2
    assert amount_changed.fingerprint != first.fingerprint
    recipient_changed = amount_changed.revise(
        profile_id=first.profile_id,
        amount=amount_changed.amount,
        recipient_code="new-payee",
        now=NOW + timedelta(seconds=2),
    )
    amount_changed.assert_successor(recipient_changed)
    assert recipient_changed.revision == 3
    assert recipient_changed.fingerprint != amount_changed.fingerprint
    profile_changed = recipient_changed.revise(
        profile_id=_id(5),
        amount=recipient_changed.amount,
        recipient_code=recipient_changed.recipient_code,
        now=NOW + timedelta(seconds=3),
    )
    assert profile_changed.fingerprint != recipient_changed.fingerprint
    restored_fields = profile_changed.revise(
        profile_id=first.profile_id,
        amount=first.amount,
        recipient_code=first.recipient_code,
        now=NOW + timedelta(seconds=4),
    )
    assert restored_fields.fingerprint == first.fingerprint
    assert restored_fields.revision == 5  # revision still rejects the old check


def test_invalid_values_terminal_states_and_mismatched_bank_result() -> None:
    draft = _draft()
    with pytest.raises(ValueError, match="synthetic code"):
        transfer_fingerprint(draft.profile_id, draft.amount, "user@example.com")
    with pytest.raises(ValueError, match="fingerprint"):
        replace(draft, fingerprint="0" * 64)
    with pytest.raises(ValueError, match="terminal"):
        replace(draft, status=IntentStatus.EXECUTED).revise(
            profile_id=draft.profile_id,
            amount=draft.amount,
            recipient_code="new-payee",
            now=NOW,
        )
    with pytest.raises(ValueError, match="advance"):
        replace(draft, status=IntentStatus.CANCELLED).assert_successor(
            draft.revise(
                profile_id=draft.profile_id,
                amount=draft.amount,
                recipient_code="new-payee",
                now=NOW,
            )
        )
    with pytest.raises(ValueError, match="revision time"):
        draft.revise(
            profile_id=draft.profile_id,
            amount=draft.amount,
            recipient_code="new-payee",
            now=NOW - timedelta(seconds=1),
        )
    result = DemoBankResult(
        operation_id=_id(9),
        intent_id=draft.intent_id,
        intent_revision=draft.revision,
        intent_fingerprint=draft.fingerprint,
        profile_id=draft.profile_id,
        amount=draft.amount,
        recipient_code=draft.recipient_code,
        status=DemoBankStatus.EXECUTED,
        recorded_at=NOW,
    )
    assert result.amount.amount_minor == 120_000
    with pytest.raises(ValueError, match="differs"):
        replace(result, amount=Money(200_000, Currency.RUB))
