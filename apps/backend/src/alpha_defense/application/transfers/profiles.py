"""Provision reviewed synthetic templates and evaluate owner-scoped history."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    EventEnvelope,
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    IdGenerator,
)
from alpha_defense.application.ports.financial_profiles import ProfileUnitOfWorkFactory
from alpha_defense.application.shared import (
    ActionInProgressError,
    ActorContext,
    ConsentRequiredError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from alpha_defense.domain.identity import ConsentScope, ConsentStatus
from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import (
    BehaviorFeatures,
    CompletedOperation,
    FinancialProfile,
    assess_history,
)

_CODE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


@dataclass(frozen=True, slots=True)
class TemplateOperation:
    days_before_creation: int
    amount_minor: int
    recipient_code: str

    def __post_init__(self) -> None:
        if type(self.days_before_creation) is not int or not 1 <= self.days_before_creation <= 90:
            raise ValueError("template history must be within 90 days")
        Money(self.amount_minor, Currency.RUB)
        if not isinstance(self.recipient_code, str) or not _CODE.fullmatch(self.recipient_code):
            raise ValueError("recipient_code must be a synthetic code")


@dataclass(frozen=True, slots=True)
class ProfileTemplate:
    code: str
    version: str
    title: str
    description: str
    operations: tuple[TemplateOperation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not _CODE.fullmatch(self.code):
            raise ValueError("template code is invalid")
        for name, limit in (("version", 64), ("title", 160), ("description", 500)):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or len(value) > limit
            ):
                raise ValueError(f"template {name} is invalid")
        if not isinstance(self.operations, tuple) or any(
            not isinstance(item, TemplateOperation) for item in self.operations
        ):
            raise TypeError("template operations must be TemplateOperation values")
        if len({item.days_before_creation for item in self.operations}) != len(self.operations):
            raise ValueError("template days must be unique")


class TemplatePort(Protocol):
    def list_templates(self) -> tuple[ProfileTemplate, ...]: ...

    def get_template(self, code: str) -> ProfileTemplate | None: ...


class FinancialProfiles:
    def __init__(
        self,
        *,
        unit_of_work: ProfileUnitOfWorkFactory,
        templates: TemplatePort,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._templates = templates
        self._clock = clock
        self._ids = id_generator

    def list_templates(self) -> tuple[ProfileTemplate, ...]:
        return self._templates.list_templates()

    def list_owned(self, *, actor: ActorContext) -> tuple[FinancialProfile, ...]:
        with self._unit_of_work() as uow:
            return uow.profiles.list_owned(owner_id=actor.user_id, namespace_id=actor.namespace_id)

    def get(self, *, actor: ActorContext, profile_id: EntityId) -> FinancialProfile:
        with self._unit_of_work() as uow:
            profile = uow.profiles.get(profile_id)
        if profile is None or not _owned(profile, actor):
            raise ResourceNotFoundError("Профиль не найден.")
        return profile

    def create_from_template(
        self, *, actor: ActorContext, template_code: str, idempotency_key: str
    ) -> FinancialProfile:
        now = self._clock.now_utc()
        with self._unit_of_work() as uow:
            profile_id = EntityId(
                uuid5(
                    NAMESPACE_URL,
                    f"alpha-defense-profile:{actor.user_id}:{actor.namespace_id}:{template_code}",
                )
            )
            candidate = IdempotencyRecord(
                record_id=self._ids.new_id(),
                scope=IdempotencyScope(
                    principal_fingerprint=sha256(str(actor.user_id).encode()).hexdigest(),
                    session_id=actor.session_id,
                    namespace_id=actor.namespace_id,
                    method="POST",
                    canonical_route="/api/v1/profiles",
                    key=idempotency_key,
                ),
                command_hash=sha256(template_code.encode()).hexdigest(),
                resource_id=profile_id,
                state=IdempotencyState.IN_PROGRESS,
                result=None,
                revision=0,
                created_at=now,
                updated_at=now,
            )
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                if reservation.record.state is not IdempotencyState.COMPLETED:
                    raise ActionInProgressError("Создание профиля ещё не завершено.")
                replay = uow.profiles.get(reservation.record.resource_id)
                if replay is None or not _owned(replay, actor):
                    raise ServiceUnavailableError("Сохранённый профиль недоступен.")
                return replay
            template = self._templates.get_template(template_code)
            if template is None:
                raise ValidationError("Неизвестный демонстрационный профиль.")
            profile = uow.profiles.get_by_template(
                owner_id=actor.user_id,
                namespace_id=actor.namespace_id,
                template_code=template_code,
            )
            if profile is None:
                profile = self._instantiate(actor, template, profile_id, now)
                uow.profiles.add(profile)
                uow.audit.append(
                    AuditRecord(
                        event=EventEnvelope(
                            event_id=self._ids.new_id(),
                            event_type="profile.created",
                            aggregate_id=profile.profile_id,
                            aggregate_revision=profile.history_version,
                            occurred_at=now,
                            correlation_id=profile.profile_id,
                            execution_mode=actor.execution_mode,
                            payload={
                                "template_code": profile.template_code,
                                "template_version": profile.template_version,
                                "operation_count": len(profile.operations),
                            },
                        ),
                        recorded_at=now,
                        actor_id=actor.user_id,
                        session_id=actor.session_id,
                        namespace_id=actor.namespace_id,
                    )
                )
            uow.idempotency.save(
                candidate.finish(
                    state=IdempotencyState.COMPLETED,
                    result={"profile_id": str(profile.profile_id)},
                    updated_at=now,
                ),
                expected_revision=0,
            )
            uow.commit()
            return profile

    def evaluate(
        self,
        *,
        actor: ActorContext,
        profile_id: EntityId,
        amount: Money,
        recipient_code: str,
        as_of: datetime,
    ) -> BehaviorFeatures:
        with self._unit_of_work() as uow:
            profile = uow.profiles.get(profile_id)
            if profile is None or not _owned(profile, actor):
                raise ResourceNotFoundError("Профиль не найден.")
            consent = uow.identity.get_consent(actor.user_id, ConsentScope.USE_TRANSACTION_HISTORY)
            if consent is None or consent.status is not ConsentStatus.GRANTED:
                raise ConsentRequiredError("Разрешите использование истории операций.")
        return assess_history(profile, amount=amount, recipient_code=recipient_code, as_of=as_of)

    def _instantiate(
        self,
        actor: ActorContext,
        template: ProfileTemplate,
        profile_id: EntityId,
        now: datetime,
    ) -> FinancialProfile:
        operations = tuple(
            sorted(
                (
                    CompletedOperation(
                        operation_id=self._ids.new_id(),
                        profile_id=profile_id,
                        amount=Money(item.amount_minor, Currency.RUB),
                        recipient_code=item.recipient_code,
                        completed_at=now - timedelta(days=item.days_before_creation),
                    )
                    for item in template.operations
                ),
                key=lambda item: (item.completed_at, str(item.operation_id)),
            )
        )
        return FinancialProfile(
            profile_id=profile_id,
            owner_id=actor.user_id,
            namespace_id=actor.namespace_id,
            template_code=template.code,
            template_version=template.version,
            title=template.title,
            description=template.description,
            history_version=1,
            created_at=now,
            operations=operations,
        )


def _owned(profile: FinancialProfile, actor: ActorContext) -> bool:
    return profile.owner_id == actor.user_id and profile.namespace_id == actor.namespace_id
