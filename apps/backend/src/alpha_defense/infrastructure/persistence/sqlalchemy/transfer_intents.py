"""SQLite draft CAS and synchronous, transaction-local demo-bank adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.shared import ServiceUnavailableError, StaleRevisionError
from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import (
    DemoBankResult,
    DemoBankStatus,
    IntentStatus,
    TransferIntent,
)
from alpha_defense.infrastructure.persistence.sqlalchemy.mappers import as_utc
from alpha_defense.infrastructure.persistence.sqlalchemy.schema import (
    demo_bank_results,
    transfer_intents,
)


class SqlAlchemyTransferIntentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, intent_id: EntityId) -> TransferIntent | None:
        row = (
            self._session.execute(
                sa.select(transfer_intents).where(transfer_intents.c.intent_id == str(intent_id))
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _intent_from_row(row)

    def list_owned(
        self, *, owner_id: EntityId, namespace_id: EntityId
    ) -> tuple[TransferIntent, ...]:
        rows = (
            self._session.execute(
                sa.select(transfer_intents)
                .where(
                    transfer_intents.c.owner_id == str(owner_id),
                    transfer_intents.c.namespace_id == str(namespace_id),
                )
                .order_by(transfer_intents.c.created_at, transfer_intents.c.intent_id)
            )
            .mappings()
            .all()
        )
        return tuple(_intent_from_row(row) for row in rows)

    def add(self, intent: TransferIntent) -> None:
        try:
            self._session.execute(sa.insert(transfer_intents).values(_intent_values(intent)))
        except SQLAlchemyError as exc:
            raise ServiceUnavailableError("Local transfer persistence failed") from exc

    def save(self, intent: TransferIntent, *, expected_revision: int) -> None:
        current = self.get(intent.intent_id)
        if current is None or current.revision != expected_revision:
            raise StaleRevisionError("Transfer intent revision is stale")
        current.assert_successor(intent)
        try:
            result = self._session.execute(
                sa.update(transfer_intents)
                .where(
                    transfer_intents.c.intent_id == str(intent.intent_id),
                    transfer_intents.c.revision == expected_revision,
                )
                .values(_intent_values(intent))
            )
        except SQLAlchemyError as exc:
            raise ServiceUnavailableError("Local transfer persistence failed") from exc
        if cast(CursorResult[Any], result).rowcount != 1:
            raise StaleRevisionError("Transfer intent revision is stale")


class SqlAlchemyDemoBank:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_intent(self, intent_id: EntityId) -> DemoBankResult | None:
        row = (
            self._session.execute(
                sa.select(demo_bank_results).where(demo_bank_results.c.intent_id == str(intent_id))
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _result_from_row(row)

    def record(
        self, intent: TransferIntent, *, operation_id: EntityId, recorded_at: datetime
    ) -> DemoBankResult:
        if intent.status is not IntentStatus.CHECKED:
            raise ValueError("only a checked intent may reach the local bank")
        current = SqlAlchemyTransferIntentRepository(self._session).get(intent.intent_id)
        if current != intent:
            raise StaleRevisionError("Transfer intent changed before bank recording")
        existing = self.get_by_intent(intent.intent_id)
        if existing is not None:
            return _same_result(existing, intent)
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
        try:
            statement = sqlite_insert(demo_bank_results).values(
                operation_id=str(result.operation_id),
                intent_id=str(result.intent_id),
                intent_revision=result.intent_revision,
                intent_fingerprint=result.intent_fingerprint,
                profile_id=str(result.profile_id),
                amount_minor=result.amount.amount_minor,
                currency=result.amount.currency.value,
                recipient_code=result.recipient_code,
                status=result.status.value,
                recorded_at=result.recorded_at,
            )
            inserted = self._session.execute(statement.on_conflict_do_nothing())
        except SQLAlchemyError as exc:
            raise ServiceUnavailableError("Local bank persistence failed") from exc
        if cast(CursorResult[Any], inserted).rowcount == 1:
            return result
        existing = self.get_by_intent(intent.intent_id)
        if existing is None:
            raise ServiceUnavailableError("Local bank operation ID conflicts")
        return _same_result(existing, intent)


def _same_result(result: DemoBankResult, intent: TransferIntent) -> DemoBankResult:
    if result.intent_revision != intent.revision or result.intent_fingerprint != intent.fingerprint:
        raise StaleRevisionError("Intent already has a different bank result")
    return result


def _intent_values(intent: TransferIntent) -> dict[str, object]:
    return {
        "intent_id": str(intent.intent_id),
        "owner_id": str(intent.owner_id),
        "namespace_id": str(intent.namespace_id),
        "profile_id": str(intent.profile_id),
        "amount_minor": intent.amount.amount_minor,
        "currency": intent.amount.currency.value,
        "recipient_code": intent.recipient_code,
        "revision": intent.revision,
        "fingerprint": intent.fingerprint,
        "status": intent.status.value,
        "created_at": intent.created_at,
        "updated_at": intent.updated_at,
    }


def _intent_from_row(row: RowMapping) -> TransferIntent:
    try:
        return TransferIntent(
            intent_id=EntityId.from_string(row["intent_id"]),
            owner_id=EntityId.from_string(row["owner_id"]),
            namespace_id=EntityId.from_string(row["namespace_id"]),
            profile_id=EntityId.from_string(row["profile_id"]),
            amount=Money(row["amount_minor"], Currency(row["currency"])),
            recipient_code=row["recipient_code"],
            revision=row["revision"],
            fingerprint=row["fingerprint"],
            status=IntentStatus(row["status"]),
            created_at=as_utc(row["created_at"]),
            updated_at=as_utc(row["updated_at"]),
        )
    except (TypeError, ValueError) as exc:
        raise ServiceUnavailableError("Stored transfer intent is invalid") from exc


def _result_from_row(row: RowMapping) -> DemoBankResult:
    try:
        return DemoBankResult(
            operation_id=EntityId.from_string(row["operation_id"]),
            intent_id=EntityId.from_string(row["intent_id"]),
            intent_revision=row["intent_revision"],
            intent_fingerprint=row["intent_fingerprint"],
            profile_id=EntityId.from_string(row["profile_id"]),
            amount=Money(row["amount_minor"], Currency(row["currency"])),
            recipient_code=row["recipient_code"],
            status=DemoBankStatus(row["status"]),
            recorded_at=as_utc(row["recorded_at"]),
        )
    except (TypeError, ValueError) as exc:
        raise ServiceUnavailableError("Stored demo bank result is invalid") from exc
