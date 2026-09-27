"""Owner-scoped draft commands; checking and execution are later workflows."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import cast

from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    EventEnvelope,
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    IdGenerator,
)
from alpha_defense.application.ports.transfer_intents import (
    TransferUnitOfWorkFactory,
    TransferUnitOfWorkPort,
)
from alpha_defense.application.shared import (
    ActionInProgressError,
    ActorContext,
    ResourceNotFoundError,
    ServiceUnavailableError,
    StaleRevisionError,
    ValidationError,
)
from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import IntentStatus, TransferIntent, transfer_fingerprint


class TransferIntents:
    def __init__(
        self, *, unit_of_work: TransferUnitOfWorkFactory, clock: Clock, id_generator: IdGenerator
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = id_generator

    def list_owned(self, *, actor: ActorContext) -> tuple[TransferIntent, ...]:
        with self._unit_of_work() as uow:
            return uow.transfer_intents.list_owned(
                owner_id=actor.user_id, namespace_id=actor.namespace_id
            )

    def get(self, *, actor: ActorContext, intent_id: EntityId) -> TransferIntent:
        with self._unit_of_work() as uow:
            return _owned_intent(uow, actor, intent_id)

    def create(
        self,
        *,
        actor: ActorContext,
        profile_id: EntityId,
        amount: Money,
        recipient_code: str,
        idempotency_key: str,
    ) -> TransferIntent:
        try:
            transfer_fingerprint(profile_id, amount, recipient_code)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Некорректные данные демонстрационного перевода.") from exc
        now = self._clock.now_utc()
        with self._unit_of_work() as uow:
            candidate = self._candidate(
                actor=actor,
                key=idempotency_key,
                method="POST",
                route="/api/v1/transfer-intents",
                command={
                    "profile_id": str(profile_id),
                    "amount_minor": amount.amount_minor,
                    "recipient_code": recipient_code,
                },
                resource_id=self._ids.new_id(),
                now=now,
            )
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                if reservation.record.state is not IdempotencyState.COMPLETED:
                    raise ActionInProgressError("Создание перевода ещё не завершено.")
                _owned_intent(uow, actor, reservation.record.resource_id)
                return _restore_intent(reservation.record.result)
            _owned_profile(uow, actor, profile_id)
            intent = TransferIntent.draft(
                intent_id=candidate.resource_id,
                owner_id=actor.user_id,
                namespace_id=actor.namespace_id,
                profile_id=profile_id,
                amount=amount,
                recipient_code=recipient_code,
                now=now,
            )
            uow.transfer_intents.add(intent)
            self._audit(uow, actor, intent, "transfer.intent.created", now)
            uow.idempotency.save(
                candidate.finish(
                    state=IdempotencyState.COMPLETED,
                    result=_snapshot(intent),
                    updated_at=now,
                ),
                expected_revision=0,
            )
            uow.commit()
            return intent

    def revise(
        self,
        *,
        actor: ActorContext,
        intent_id: EntityId,
        expected_revision: int,
        profile_id: EntityId,
        amount: Money,
        recipient_code: str,
        idempotency_key: str,
    ) -> TransferIntent:
        try:
            transfer_fingerprint(profile_id, amount, recipient_code)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Некорректные данные демонстрационного перевода.") from exc
        now = self._clock.now_utc()
        with self._unit_of_work() as uow:
            current = _owned_intent(uow, actor, intent_id)
            candidate = self._candidate(
                actor=actor,
                key=idempotency_key,
                method="PATCH",
                route="/api/v1/transfer-intents/{intent_id}",
                command={
                    "intent_id": str(intent_id),
                    "expected_revision": expected_revision,
                    "profile_id": str(profile_id),
                    "amount_minor": amount.amount_minor,
                    "recipient_code": recipient_code,
                },
                resource_id=intent_id,
                now=now,
            )
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                if reservation.record.state is not IdempotencyState.COMPLETED:
                    raise ActionInProgressError("Изменение перевода ещё не завершено.")
                return _restore_intent(reservation.record.result)
            if current.revision != expected_revision:
                raise StaleRevisionError("Версия перевода устарела.")
            _owned_profile(uow, actor, profile_id)
            try:
                updated = current.revise(
                    profile_id=profile_id,
                    amount=amount,
                    recipient_code=recipient_code,
                    now=now,
                )
            except ValueError as exc:
                raise ValidationError("Этот перевод больше нельзя изменять.") from exc
            if updated != current:
                uow.transfer_intents.save(updated, expected_revision=current.revision)
                self._audit(uow, actor, updated, "transfer.intent.revised", now)
            uow.idempotency.save(
                candidate.finish(
                    state=IdempotencyState.COMPLETED,
                    result=_snapshot(updated),
                    updated_at=now,
                ),
                expected_revision=0,
            )
            uow.commit()
            return updated

    def _candidate(
        self,
        *,
        actor: ActorContext,
        key: str,
        method: str,
        route: str,
        command: dict[str, str | int],
        resource_id: EntityId,
        now: datetime,
    ) -> IdempotencyRecord:
        command_hash = sha256(
            json.dumps(command, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return IdempotencyRecord(
            record_id=self._ids.new_id(),
            scope=IdempotencyScope(
                principal_fingerprint=sha256(str(actor.user_id).encode()).hexdigest(),
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                method=method,
                canonical_route=route,
                key=key,
            ),
            command_hash=command_hash,
            resource_id=resource_id,
            state=IdempotencyState.IN_PROGRESS,
            result=None,
            revision=0,
            created_at=now,
            updated_at=now,
        )

    def _audit(
        self,
        uow: TransferUnitOfWorkPort,
        actor: ActorContext,
        intent: TransferIntent,
        event_type: str,
        now: datetime,
    ) -> None:
        uow.audit.append(
            AuditRecord(
                event=EventEnvelope(
                    event_id=self._ids.new_id(),
                    event_type=event_type,
                    aggregate_id=intent.intent_id,
                    aggregate_revision=intent.revision,
                    occurred_at=now,
                    correlation_id=intent.intent_id,
                    execution_mode=actor.execution_mode,
                    payload={
                        "profile_id": str(intent.profile_id),
                        "revision": intent.revision,
                        "fingerprint": intent.fingerprint,
                    },
                ),
                recorded_at=now,
                actor_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
            )
        )


def _owned_profile(uow: TransferUnitOfWorkPort, actor: ActorContext, profile_id: EntityId) -> None:
    profile = uow.profiles.get(profile_id)
    if (
        profile is None
        or profile.owner_id != actor.user_id
        or profile.namespace_id != actor.namespace_id
    ):
        raise ResourceNotFoundError("Профиль не найден.")


def _owned_intent(
    uow: TransferUnitOfWorkPort, actor: ActorContext, intent_id: EntityId
) -> TransferIntent:
    intent = uow.transfer_intents.get(intent_id)
    if (
        intent is None
        or intent.owner_id != actor.user_id
        or intent.namespace_id != actor.namespace_id
    ):
        raise ResourceNotFoundError("Перевод не найден.")
    return intent


def _snapshot(intent: TransferIntent) -> dict[str, str | int]:
    return {
        "intent_id": str(intent.intent_id),
        "owner_id": str(intent.owner_id),
        "namespace_id": str(intent.namespace_id),
        "profile_id": str(intent.profile_id),
        "amount_minor": intent.amount.amount_minor,
        "recipient_code": intent.recipient_code,
        "revision": intent.revision,
        "fingerprint": intent.fingerprint,
        "status": intent.status.value,
        "created_at": intent.created_at.isoformat(),
        "updated_at": intent.updated_at.isoformat(),
    }


def _restore_intent(result: object) -> TransferIntent:
    if not isinstance(result, dict):
        raise ServiceUnavailableError("Сохранённый результат изменения недоступен.")
    values = cast(dict[str, object], result)
    try:
        return TransferIntent(
            intent_id=EntityId.from_string(str(values["intent_id"])),
            owner_id=EntityId.from_string(str(values["owner_id"])),
            namespace_id=EntityId.from_string(str(values["namespace_id"])),
            profile_id=EntityId.from_string(str(values["profile_id"])),
            amount=Money(int(cast(int, values["amount_minor"])), Currency.RUB),
            recipient_code=str(values["recipient_code"]),
            revision=int(cast(int, values["revision"])),
            fingerprint=str(values["fingerprint"]),
            status=IntentStatus(str(values["status"])),
            created_at=datetime.fromisoformat(str(values["created_at"])),
            updated_at=datetime.fromisoformat(str(values["updated_at"])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceUnavailableError("Сохранённый результат изменения повреждён.") from exc
