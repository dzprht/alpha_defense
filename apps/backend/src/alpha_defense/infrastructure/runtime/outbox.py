"""Transactional enqueueing and at-least-once durable outbox dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from alpha_defense.application.ports import (
    Clock,
    EventEnvelope,
    EventHandler,
    IdGenerator,
    OutboxMessage,
    OutboxReceipt,
    OutboxRepositoryPort,
    OutboxState,
    UnitOfWorkFactory,
)
from alpha_defense.application.ports.events import validate_topic


class TransactionalEventSink:
    """Append to the outbox owned by an already active UnitOfWork."""

    def __init__(
        self,
        repository: OutboxRepositoryPort,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._id_generator = id_generator

    def append(self, event: EventEnvelope, *, topic: str) -> OutboxReceipt:
        validate_topic(topic)
        now = self._clock.now_utc()
        message = OutboxMessage(
            message_id=self._id_generator.new_id(),
            event=event,
            topic=topic,
            state=OutboxState.PENDING,
            attempts=0,
            next_attempt_at=now,
            lease_expires_at=None,
            delivered_at=None,
            last_error_code=None,
            revision=0,
            created_at=now,
        )
        self._repository.add(message)
        return OutboxReceipt(message_id=message.message_id, accepted_at=now)


@dataclass(frozen=True, slots=True)
class DispatchReport:
    claimed: int = 0
    delivered: int = 0
    rescheduled: int = 0
    missing_handlers: int = 0


class OutboxDispatcher:
    """Claim durably, invoke handlers outside SQL, then persist the outcome."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        *,
        lease_duration: timedelta = timedelta(seconds=30),
        retry_delay: timedelta = timedelta(seconds=5),
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if retry_delay <= timedelta(0):
            raise ValueError("retry_delay must be positive")
        self._uow_factory = uow_factory
        self._clock = clock
        self._lease_duration = lease_duration
        self._retry_delay = retry_delay
        self._handlers: dict[str, EventHandler] = {}

    def register(self, topic: str, handler: EventHandler) -> None:
        validate_topic(topic)
        if topic in self._handlers:
            raise ValueError(f"handler is already registered for topic {topic!r}")
        self._handlers[topic] = handler

    def dispatch_once(self, *, limit: int = 100) -> DispatchReport:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        claimed = delivered = rescheduled = missing_handlers = 0
        for _ in range(limit):
            message = self._claim_one()
            if message is None:
                break
            claimed += 1
            handler = self._handlers.get(message.topic)
            if handler is None:
                missing_handlers += 1
                self._reschedule(message, error_code="handler_not_registered")
                rescheduled += 1
                continue
            try:
                handler(message.event)
            except Exception:
                self._reschedule(message, error_code="handler_failed")
                rescheduled += 1
            else:
                self._mark_delivered(message)
                delivered += 1
        return DispatchReport(
            claimed=claimed,
            delivered=delivered,
            rescheduled=rescheduled,
            missing_handlers=missing_handlers,
        )

    def _claim_one(self) -> OutboxMessage | None:
        now = self._clock.now_utc()
        with self._uow_factory() as uow:
            message = uow.outbox.claim_next(
                now=now,
                lease_expires_at=now + self._lease_duration,
            )
            uow.commit()
        return message

    def _mark_delivered(self, message: OutboxMessage) -> None:
        with self._uow_factory() as uow:
            uow.outbox.mark_delivered(
                message.message_id,
                expected_revision=message.revision,
                delivered_at=self._clock.now_utc(),
            )
            uow.commit()

    def _reschedule(self, message: OutboxMessage, *, error_code: str) -> None:
        now = self._clock.now_utc()
        with self._uow_factory() as uow:
            uow.outbox.reschedule(
                message.message_id,
                expected_revision=message.revision,
                next_attempt_at=now + self._retry_delay,
                error_code=error_code,
            )
            uow.commit()
