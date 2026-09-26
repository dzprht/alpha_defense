"""SQLite profiles with an append-only completed-operation table."""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.shared import ServiceUnavailableError, StaleRevisionError
from alpha_defense.domain.shared import Currency, EntityId, Money
from alpha_defense.domain.transfers import CompletedOperation, FinancialProfile
from alpha_defense.infrastructure.persistence.sqlalchemy.mappers import as_utc
from alpha_defense.infrastructure.persistence.sqlalchemy.schema import (
    completed_operations,
    financial_profiles,
)


class SqlAlchemyProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, profile_id: EntityId) -> FinancialProfile | None:
        row = (
            self._session.execute(
                sa.select(financial_profiles).where(
                    financial_profiles.c.profile_id == str(profile_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._from_row(row)

    def get_by_template(
        self, *, owner_id: EntityId, namespace_id: EntityId, template_code: str
    ) -> FinancialProfile | None:
        row = self._session.execute(
            sa.select(financial_profiles.c.profile_id).where(
                financial_profiles.c.owner_id == str(owner_id),
                financial_profiles.c.namespace_id == str(namespace_id),
                financial_profiles.c.template_code == template_code,
            )
        ).scalar_one_or_none()
        return None if row is None else self.get(EntityId.from_string(row))

    def list_owned(
        self, *, owner_id: EntityId, namespace_id: EntityId
    ) -> tuple[FinancialProfile, ...]:
        ids = self._session.execute(
            sa.select(financial_profiles.c.profile_id)
            .where(
                financial_profiles.c.owner_id == str(owner_id),
                financial_profiles.c.namespace_id == str(namespace_id),
            )
            .order_by(financial_profiles.c.created_at, financial_profiles.c.profile_id)
        ).scalars()
        return tuple(
            profile
            for raw_id in ids
            if (profile := self.get(EntityId.from_string(raw_id))) is not None
        )

    def add(self, profile: FinancialProfile) -> None:
        try:
            self._session.execute(
                sa.insert(financial_profiles).values(
                    profile_id=str(profile.profile_id),
                    owner_id=str(profile.owner_id),
                    namespace_id=str(profile.namespace_id),
                    template_code=profile.template_code,
                    template_version=profile.template_version,
                    title=profile.title,
                    description=profile.description,
                    history_version=profile.history_version,
                    created_at=profile.created_at,
                )
            )
            for ordinal, operation in enumerate(profile.operations):
                self._insert_operation(operation, ordinal)
        except SQLAlchemyError as exc:
            raise ServiceUnavailableError("Local profile persistence failed") from exc

    def append_completed(self, profile: FinancialProfile, *, expected_version: int) -> None:
        current = self.get(profile.profile_id)
        if current is None or current.history_version != expected_version:
            raise StaleRevisionError("Profile version is stale")
        current.assert_successor(profile)
        try:
            result = self._session.execute(
                sa.update(financial_profiles)
                .where(
                    financial_profiles.c.profile_id == str(profile.profile_id),
                    financial_profiles.c.history_version == expected_version,
                )
                .values(history_version=profile.history_version)
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                raise StaleRevisionError("Profile version is stale")
            self._insert_operation(profile.operations[-1], len(current.operations))
        except SQLAlchemyError as exc:
            raise ServiceUnavailableError("Local profile persistence failed") from exc

    def _insert_operation(self, operation: CompletedOperation, ordinal: int) -> None:
        self._session.execute(
            sa.insert(completed_operations).values(
                operation_id=str(operation.operation_id),
                profile_id=str(operation.profile_id),
                ordinal=ordinal,
                amount_minor=operation.amount.amount_minor,
                currency=operation.amount.currency.value,
                recipient_code=operation.recipient_code,
                completed_at=operation.completed_at,
            )
        )

    def _from_row(self, row: RowMapping) -> FinancialProfile:
        operation_rows = tuple(
            self._session.execute(
                sa.select(completed_operations)
                .where(completed_operations.c.profile_id == row["profile_id"])
                .order_by(completed_operations.c.ordinal)
            ).mappings()
        )
        if any(item["ordinal"] != index for index, item in enumerate(operation_rows)):
            raise ServiceUnavailableError("Stored financial profile history is invalid")
        try:
            return FinancialProfile(
                profile_id=EntityId.from_string(row["profile_id"]),
                owner_id=EntityId.from_string(row["owner_id"]),
                namespace_id=EntityId.from_string(row["namespace_id"]),
                template_code=row["template_code"],
                template_version=row["template_version"],
                title=row["title"],
                description=row["description"],
                history_version=row["history_version"],
                created_at=as_utc(row["created_at"]),
                operations=tuple(
                    CompletedOperation(
                        operation_id=EntityId.from_string(item["operation_id"]),
                        profile_id=EntityId.from_string(item["profile_id"]),
                        amount=Money(item["amount_minor"], Currency(item["currency"])),
                        recipient_code=item["recipient_code"],
                        completed_at=as_utc(item["completed_at"]),
                    )
                    for item in operation_rows
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ServiceUnavailableError("Stored financial profile is invalid") from exc
