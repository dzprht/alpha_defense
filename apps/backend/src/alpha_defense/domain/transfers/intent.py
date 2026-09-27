"""Versioned synthetic transfer intent and a durable local-bank outcome."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256

from alpha_defense.domain.shared import EntityId, Money

_RECIPIENT = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _require_utc(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


def transfer_fingerprint(profile_id: EntityId, amount: Money, recipient_code: str) -> str:
    """Bind a check to exactly the material transfer fields, not to a display label."""

    if not isinstance(profile_id, EntityId) or not isinstance(amount, Money):
        raise TypeError("profile_id and amount must be typed values")
    if not isinstance(recipient_code, str) or not _RECIPIENT.fullmatch(recipient_code):
        raise ValueError("recipient_code must be a synthetic code")
    payload = {
        "amount_minor": amount.amount_minor,
        "currency": amount.currency.value,
        "profile_id": str(profile_id),
        "recipient_code": recipient_code,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class IntentStatus(StrEnum):
    DRAFT = "draft"
    CHECKED = "checked"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TransferIntent:
    intent_id: EntityId
    owner_id: EntityId
    namespace_id: EntityId
    profile_id: EntityId
    amount: Money
    recipient_code: str
    revision: int
    fingerprint: str
    status: IntentStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for name in ("intent_id", "owner_id", "namespace_id", "profile_id"):
            if not isinstance(getattr(self, name), EntityId):
                raise TypeError(f"{name} must be EntityId")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("revision must be a positive integer")
        if not isinstance(self.status, IntentStatus):
            raise TypeError("status must be IntentStatus")
        if self.fingerprint != transfer_fingerprint(
            self.profile_id, self.amount, self.recipient_code
        ):
            raise ValueError("fingerprint does not match the transfer fields")
        _require_utc(self.created_at, "created_at")
        _require_utc(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")

    @classmethod
    def draft(
        cls,
        *,
        intent_id: EntityId,
        owner_id: EntityId,
        namespace_id: EntityId,
        profile_id: EntityId,
        amount: Money,
        recipient_code: str,
        now: datetime,
    ) -> TransferIntent:
        return cls(
            intent_id=intent_id,
            owner_id=owner_id,
            namespace_id=namespace_id,
            profile_id=profile_id,
            amount=amount,
            recipient_code=recipient_code,
            revision=1,
            fingerprint=transfer_fingerprint(profile_id, amount, recipient_code),
            status=IntentStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )

    def revise(
        self, *, profile_id: EntityId, amount: Money, recipient_code: str, now: datetime
    ) -> TransferIntent:
        if self.status not in (IntentStatus.DRAFT, IntentStatus.CHECKED):
            raise ValueError("a terminal intent cannot be revised")
        _require_utc(now, "now")
        if now < self.updated_at:
            raise ValueError("revision time cannot move backwards")
        fingerprint = transfer_fingerprint(profile_id, amount, recipient_code)
        if fingerprint == self.fingerprint:
            return self
        return replace(
            self,
            profile_id=profile_id,
            amount=amount,
            recipient_code=recipient_code,
            revision=self.revision + 1,
            fingerprint=fingerprint,
            status=IntentStatus.DRAFT,
            updated_at=now,
        )

    def assert_successor(self, newer: TransferIntent) -> None:
        if (
            self.status not in (IntentStatus.DRAFT, IntentStatus.CHECKED)
            or newer.intent_id != self.intent_id
            or newer.owner_id != self.owner_id
            or newer.namespace_id != self.namespace_id
            or newer.created_at != self.created_at
            or newer.revision != self.revision + 1
            or newer.status is not IntentStatus.DRAFT
            or newer.updated_at < self.updated_at
            or newer.fingerprint == self.fingerprint
        ):
            raise ValueError("intent revision must advance by one changed draft")


class DemoBankStatus(StrEnum):
    EXECUTED = "executed"


@dataclass(frozen=True, slots=True)
class DemoBankResult:
    operation_id: EntityId
    intent_id: EntityId
    intent_revision: int
    intent_fingerprint: str
    profile_id: EntityId
    amount: Money
    recipient_code: str
    status: DemoBankStatus
    recorded_at: datetime

    def __post_init__(self) -> None:
        for name in ("operation_id", "intent_id", "profile_id"):
            if not isinstance(getattr(self, name), EntityId):
                raise TypeError(f"{name} must be EntityId")
        if type(self.intent_revision) is not int or self.intent_revision < 1:
            raise ValueError("intent_revision must be a positive integer")
        if not isinstance(self.intent_fingerprint, str) or not _DIGEST.fullmatch(
            self.intent_fingerprint
        ):
            raise ValueError("intent_fingerprint must be SHA-256")
        if self.intent_fingerprint != transfer_fingerprint(
            self.profile_id, self.amount, self.recipient_code
        ):
            raise ValueError("bank result differs from the intent fingerprint")
        if self.status is not DemoBankStatus.EXECUTED:
            raise ValueError("local bank result must be executed")
        _require_utc(self.recorded_at, "recorded_at")
