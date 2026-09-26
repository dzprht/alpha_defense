"""Immutable synthetic history and deterministic, non-fraud behavior features."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from alpha_defense.domain.shared import EntityId, Money

HISTORY_WINDOW = timedelta(days=90)
MIN_HISTORY_SIZE = 10
AMOUNT_OUTLIER_MULTIPLIER = 3
_CODE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def _utc(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be UTC")


@dataclass(frozen=True, slots=True)
class CompletedOperation:
    operation_id: EntityId
    profile_id: EntityId
    amount: Money
    recipient_code: str
    completed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, EntityId) or not isinstance(self.profile_id, EntityId):
            raise TypeError("operation and profile IDs must be EntityId")
        if not isinstance(self.amount, Money):
            raise TypeError("amount must be Money")
        if not isinstance(self.recipient_code, str) or not _CODE.fullmatch(self.recipient_code):
            raise ValueError("recipient_code must be a synthetic code")
        _utc(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class FinancialProfile:
    profile_id: EntityId
    owner_id: EntityId
    namespace_id: EntityId
    template_code: str
    template_version: str
    title: str
    description: str
    history_version: int
    created_at: datetime
    operations: tuple[CompletedOperation, ...]

    def __post_init__(self) -> None:
        for name in ("profile_id", "owner_id", "namespace_id"):
            if not isinstance(getattr(self, name), EntityId):
                raise TypeError(f"{name} must be EntityId")
        if not isinstance(self.template_code, str) or not _CODE.fullmatch(self.template_code):
            raise ValueError("template_code must be a synthetic code")
        if (
            not isinstance(self.template_version, str)
            or not self.template_version
            or len(self.template_version) > 64
        ):
            raise ValueError("template_version is required")
        for name, limit in (("title", 160), ("description", 500)):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or len(value) > limit
            ):
                raise ValueError(f"{name} must be non-empty and trimmed")
        if type(self.history_version) is not int or self.history_version < 1:
            raise ValueError("history_version must be a positive integer")
        _utc(self.created_at, "created_at")
        if not isinstance(self.operations, tuple) or any(
            not isinstance(item, CompletedOperation) for item in self.operations
        ):
            raise TypeError("operations must be a tuple of CompletedOperation")
        if any(item.profile_id != self.profile_id for item in self.operations):
            raise ValueError("operation belongs to a different profile")
        if len({item.operation_id for item in self.operations}) != len(self.operations):
            raise ValueError("operation IDs must be unique")
        if tuple(sorted(self.operations, key=_operation_order)) != self.operations:
            raise ValueError("operations must be ordered by completion time and ID")

    def append_completed(self, operation: CompletedOperation) -> FinancialProfile:
        """Append only; the prefix and its historical evidence never change."""

        if operation.profile_id != self.profile_id:
            raise ValueError("operation belongs to a different profile")
        if any(item.operation_id == operation.operation_id for item in self.operations):
            raise ValueError("operation already exists")
        if self.operations and _operation_order(operation) <= _operation_order(self.operations[-1]):
            raise ValueError("completed operation cannot rewrite older history")
        return replace(
            self,
            history_version=self.history_version + 1,
            operations=(*self.operations, operation),
        )

    def assert_successor(self, newer: FinancialProfile) -> None:
        if (
            newer.profile_id != self.profile_id
            or newer.owner_id != self.owner_id
            or newer.namespace_id != self.namespace_id
            or newer.template_code != self.template_code
            or newer.template_version != self.template_version
            or newer.title != self.title
            or newer.description != self.description
            or newer.created_at != self.created_at
            or newer.history_version != self.history_version + 1
            or len(newer.operations) != len(self.operations) + 1
            or newer.operations[:-1] != self.operations
        ):
            raise ValueError("profile history can only grow by one completed operation")


class HistoryStatus(StrEnum):
    COMPLETE = "complete"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class BehaviorFeatures:
    profile_id: EntityId
    profile_version: int
    status: HistoryStatus
    sample_size: int
    window_days: int
    recipient_is_new: bool | None
    amount_is_outlier: bool | None
    median_amount_minor_x2: int | None


def assess_history(
    profile: FinancialProfile,
    *,
    amount: Money,
    recipient_code: str,
    as_of: datetime,
) -> BehaviorFeatures:
    """Use completed operations strictly before the proposed transfer, never the transfer itself."""

    if not isinstance(amount, Money):
        raise TypeError("amount must be Money")
    if not isinstance(recipient_code, str) or not _CODE.fullmatch(recipient_code):
        raise ValueError("recipient_code must be a synthetic code")
    _utc(as_of, "as_of")
    history = tuple(
        item for item in profile.operations if as_of - HISTORY_WINDOW <= item.completed_at < as_of
    )
    if len(history) < MIN_HISTORY_SIZE:
        return BehaviorFeatures(
            profile_id=profile.profile_id,
            profile_version=profile.history_version,
            status=HistoryStatus.INSUFFICIENT_DATA,
            sample_size=len(history),
            window_days=HISTORY_WINDOW.days,
            recipient_is_new=None,
            amount_is_outlier=None,
            median_amount_minor_x2=None,
        )
    amounts = sorted(item.amount.amount_minor for item in history)
    middle = len(amounts) // 2
    median_x2 = 2 * amounts[middle] if len(amounts) % 2 else amounts[middle - 1] + amounts[middle]
    return BehaviorFeatures(
        profile_id=profile.profile_id,
        profile_version=profile.history_version,
        status=HistoryStatus.COMPLETE,
        sample_size=len(history),
        window_days=HISTORY_WINDOW.days,
        recipient_is_new=all(item.recipient_code != recipient_code for item in history),
        amount_is_outlier=2 * amount.amount_minor > AMOUNT_OUTLIER_MULTIPLIER * median_x2,
        median_amount_minor_x2=median_x2,
    )


def _operation_order(item: CompletedOperation) -> tuple[datetime, str]:
    return item.completed_at, str(item.operation_id)
