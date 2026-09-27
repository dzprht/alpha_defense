"""Copy-on-write drafts and exactly-one local-bank result per intent."""

from __future__ import annotations

from datetime import datetime

from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.transfers import (
    DemoBankResult,
    DemoBankStatus,
    IntentStatus,
    TransferIntent,
)
from alpha_defense.infrastructure.persistence.in_memory.store import InMemoryState


class InMemoryTransferIntentRepository:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get(self, intent_id: EntityId) -> TransferIntent | None:
        return self._state.transfer_intents.get(intent_id)

    def list_owned(
        self, *, owner_id: EntityId, namespace_id: EntityId
    ) -> tuple[TransferIntent, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._state.transfer_intents.values()
                    if item.owner_id == owner_id and item.namespace_id == namespace_id
                ),
                key=lambda item: (item.created_at, str(item.intent_id)),
            )
        )

    def add(self, intent: TransferIntent) -> None:
        if intent.intent_id in self._state.transfer_intents:
            raise ValueError("transfer intent already exists")
        self._state.transfer_intents[intent.intent_id] = intent

    def save(self, intent: TransferIntent, *, expected_revision: int) -> None:
        current = self.get(intent.intent_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Transfer intent revision is stale")
        current.assert_successor(intent)
        self._state.transfer_intents[intent.intent_id] = intent


class InMemoryDemoBank:
    def __init__(self, state: InMemoryState) -> None:
        self._state = state

    def get_by_intent(self, intent_id: EntityId) -> DemoBankResult | None:
        operation_id = self._state.demo_bank_by_intent.get(intent_id)
        return None if operation_id is None else self._state.demo_bank_results[operation_id]

    def record(
        self, intent: TransferIntent, *, operation_id: EntityId, recorded_at: datetime
    ) -> DemoBankResult:
        if intent.status is not IntentStatus.CHECKED:
            raise ValueError("only a checked intent may reach the local bank")
        current = self._state.transfer_intents.get(intent.intent_id)
        if current != intent:
            raise StaleRevisionError("Transfer intent changed before bank recording")
        existing = self.get_by_intent(intent.intent_id)
        if existing is not None:
            if (
                existing.intent_revision == intent.revision
                and existing.intent_fingerprint == intent.fingerprint
            ):
                return existing
            raise StaleRevisionError("Intent already has a different bank result")
        if operation_id in self._state.demo_bank_results:
            raise ValueError("bank operation ID already exists")
        result = DemoBankResult(
            operation_id=operation_id,
            intent_id=intent.intent_id,
            intent_revision=intent.revision,
            intent_fingerprint=intent.fingerprint,
            profile_id=intent.profile_id,
            amount=intent.amount,
            recipient_code=intent.recipient_code,
            status=DemoBankStatus.EXECUTED,
            recorded_at=recorded_at,
        )
        self._state.demo_bank_results[result.operation_id] = result
        self._state.demo_bank_by_intent[result.intent_id] = result.operation_id
        return result
