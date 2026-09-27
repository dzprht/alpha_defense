"""Atomic local execution and cancellation of synthetic transfer intents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from alpha_defense.application.ports import (
    AuditRecord,
    CatalogLoaderPort,
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
    ActionForbiddenError,
    ActionInProgressError,
    ActorContext,
    ResourceNotFoundError,
    ServiceUnavailableError,
    StaleRevisionError,
    ValidationError,
)
from alpha_defense.application.transfers.checks import current_check_view
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.transfers import (
    CheckCompleteness,
    CompletedOperation,
    DemoBankResult,
    IntentStatus,
    TransferDecision,
    TransferIntent,
)


@dataclass(frozen=True, slots=True)
class TransferCompletion:
    intent: TransferIntent
    bank_result: DemoBankResult | None


class CompleteTransfer:
    def __init__(
        self,
        *,
        unit_of_work: TransferUnitOfWorkFactory,
        catalog: CatalogLoaderPort,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._catalog = catalog
        self._clock = clock
        self._ids = id_generator

    def execute(
        self,
        *,
        actor: ActorContext,
        intent_id: EntityId,
        check_id: EntityId,
        expected_revision: int,
        acknowledge_warning: bool,
        idempotency_key: str,
    ) -> TransferCompletion:
        _revision(expected_revision)
        now = self._clock.now_utc()
        candidate = self._candidate(
            actor=actor,
            intent_id=intent_id,
            key=idempotency_key,
            action="execute",
            command={
                "check_id": str(check_id),
                "expected_revision": expected_revision,
                "acknowledge_warning": acknowledge_warning,
            },
            now=now,
        )
        with self._unit_of_work() as uow:
            intent = _owned_intent(uow, actor, intent_id)
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                if reservation.record.state is not IdempotencyState.COMPLETED:
                    raise ActionInProgressError("Исполнение перевода ещё выполняется.")
                return _completed_result(uow, intent, expected_revision)
            if intent.revision != expected_revision:
                raise StaleRevisionError("Версия перевода устарела.")
            if intent.status is IntentStatus.EXECUTED:
                latest = uow.transfer_checks.get_latest_for_intent(intent_id)
                if latest is None or latest.check_id != check_id:
                    raise StaleRevisionError("Проверка перевода изменилась.")
                result = _completed_result(uow, intent, expected_revision)
                self._save_replay(uow, candidate, result, now)
                return result
            if intent.status is not IntentStatus.CHECKED:
                raise StaleRevisionError("Для перевода нужна актуальная проверка.")
            check = uow.transfer_checks.get(check_id)
            if (
                check is None
                or check.intent_id != intent_id
                or check.owner_id != actor.user_id
                or check.namespace_id != actor.namespace_id
            ):
                raise ResourceNotFoundError("Проверка перевода не найдена.")
            policy = self._catalog.load().policy
            policy_identity = f"{policy.policy_version}:{policy.content_sha256}"
            view = current_check_view(uow, check, intent, now, policy_identity)
            if not view.fresh:
                raise StaleRevisionError(
                    "Проверка перевода устарела: " + ", ".join(view.stale_reasons)
                )
            if check.completeness is not CheckCompleteness.COMPLETE or check.decision not in (
                TransferDecision.ALLOW,
                TransferDecision.CONFIRM,
            ):
                raise ActionForbiddenError("Проверка не разрешает этот перевод.")
            if check.decision is TransferDecision.CONFIRM and not acknowledge_warning:
                raise ActionForbiddenError("Подтвердите предупреждение перед переводом.")
            profile = uow.profiles.get(intent.profile_id)
            if (
                profile is None
                or profile.owner_id != actor.user_id
                or profile.namespace_id != actor.namespace_id
            ):
                raise ResourceNotFoundError("Профиль не найден.")
            bank_result = uow.demo_bank.record(
                intent, operation_id=self._ids.new_id(), recorded_at=now
            )
            if (
                bank_result.intent_revision != intent.revision
                or bank_result.intent_fingerprint != intent.fingerprint
            ):
                raise ServiceUnavailableError("Результат банка отличается от перевода.")
            operation = CompletedOperation(
                operation_id=bank_result.operation_id,
                profile_id=intent.profile_id,
                amount=intent.amount,
                recipient_code=intent.recipient_code,
                completed_at=bank_result.recorded_at,
            )
            uow.profiles.append_completed(
                profile.append_completed(operation), expected_version=profile.history_version
            )
            updated = intent.finish(status=IntentStatus.EXECUTED, now=now)
            uow.transfer_intents.finish(updated, expected_revision=intent.revision)
            self._audit(
                uow, actor, updated, "transfer.intent.executed", now, bank_result.operation_id
            )
            result = TransferCompletion(updated, bank_result)
            self._save_replay(uow, candidate, result, now)
            return result

    def cancel(
        self,
        *,
        actor: ActorContext,
        intent_id: EntityId,
        expected_revision: int,
        idempotency_key: str,
    ) -> TransferCompletion:
        _revision(expected_revision)
        now = self._clock.now_utc()
        candidate = self._candidate(
            actor=actor,
            intent_id=intent_id,
            key=idempotency_key,
            action="cancel",
            command={"expected_revision": expected_revision},
            now=now,
        )
        with self._unit_of_work() as uow:
            intent = _owned_intent(uow, actor, intent_id)
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                if reservation.record.state is not IdempotencyState.COMPLETED:
                    raise ActionInProgressError("Отмена перевода ещё выполняется.")
                if intent.status is not IntentStatus.CANCELLED:
                    raise ServiceUnavailableError("Сохранённая отмена отличается от перевода.")
                return TransferCompletion(intent, None)
            if intent.revision != expected_revision:
                raise StaleRevisionError("Версия перевода устарела.")
            if intent.status is IntentStatus.EXECUTED:
                raise ActionForbiddenError("Выполненный перевод нельзя отменить.")
            if intent.status is IntentStatus.CANCELLED:
                result = TransferCompletion(intent, None)
                self._save_replay(uow, candidate, result, now)
                return result
            updated = intent.finish(status=IntentStatus.CANCELLED, now=now)
            uow.transfer_intents.finish(updated, expected_revision=intent.revision)
            self._audit(uow, actor, updated, "transfer.intent.cancelled", now, intent.intent_id)
            result = TransferCompletion(updated, None)
            self._save_replay(uow, candidate, result, now)
            return result

    def _candidate(
        self,
        *,
        actor: ActorContext,
        intent_id: EntityId,
        key: str,
        action: str,
        command: dict[str, str | int | bool],
        now: datetime,
    ) -> IdempotencyRecord:
        payload = {"intent_id": str(intent_id), **command}
        return IdempotencyRecord(
            record_id=self._ids.new_id(),
            scope=IdempotencyScope(
                principal_fingerprint=sha256(str(actor.user_id).encode()).hexdigest(),
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                method="POST",
                canonical_route=f"/api/v1/transfer-intents/{{intent_id}}/{action}",
                key=key,
            ),
            command_hash=sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            resource_id=intent_id,
            state=IdempotencyState.IN_PROGRESS,
            result=None,
            revision=0,
            created_at=now,
            updated_at=now,
        )

    def _save_replay(
        self,
        uow: TransferUnitOfWorkPort,
        candidate: IdempotencyRecord,
        result: TransferCompletion,
        now: datetime,
    ) -> None:
        uow.idempotency.save(
            candidate.finish(
                state=IdempotencyState.COMPLETED,
                result={
                    "intent_id": str(result.intent.intent_id),
                    "status": result.intent.status.value,
                    "operation_id": str(result.bank_result.operation_id)
                    if result.bank_result
                    else None,
                },
                updated_at=now,
            ),
            expected_revision=0,
        )
        uow.commit()

    def _audit(
        self,
        uow: TransferUnitOfWorkPort,
        actor: ActorContext,
        intent: TransferIntent,
        event_type: str,
        now: datetime,
        correlation_id: EntityId,
    ) -> None:
        uow.audit.append(
            AuditRecord(
                event=EventEnvelope(
                    event_id=self._ids.new_id(),
                    event_type=event_type,
                    aggregate_id=intent.intent_id,
                    aggregate_revision=intent.revision,
                    occurred_at=now,
                    correlation_id=correlation_id,
                    execution_mode=actor.execution_mode,
                    payload={
                        "profile_id": str(intent.profile_id),
                        "fingerprint": intent.fingerprint,
                        "status": intent.status.value,
                    },
                ),
                recorded_at=now,
                actor_id=actor.user_id,
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
            )
        )


def _revision(value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValidationError("Некорректная версия перевода.")


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


def _completed_result(
    uow: TransferUnitOfWorkPort, intent: TransferIntent, expected_revision: int
) -> TransferCompletion:
    result = uow.demo_bank.get_by_intent(intent.intent_id)
    if (
        intent.status is not IntentStatus.EXECUTED
        or intent.revision != expected_revision
        or result is None
        or result.intent_revision != intent.revision
        or result.intent_fingerprint != intent.fingerprint
    ):
        raise ServiceUnavailableError("Результат перевода не соответствует сохранённому состоянию.")
    return TransferCompletion(intent, result)
