"""Ports (interfaces) for infrastructure dependencies."""

from __future__ import annotations

from typing import Any, Protocol

from alpha_protect.domain.entities import ThreatIndicator, ThreatIndicatorType


class ThreatRegistryPort(Protocol):
    async def upsert(self, indicator: ThreatIndicator) -> None:
        ...

    async def get(self, indicator: str) -> ThreatIndicator | None:
        ...


class AlfaIdPort(Protocol):
    async def verify_call(
        self,
        phone_number: str,
        claimed_source: str,
        call_id: str | None = None,
    ) -> bool:
        ...


class OpenBankingPort(Protocol):
    async def check_operation(
        self,
        operation_id: str,
        user_id: str,
        amount: float,
    ) -> dict[str, Any]:
        ...


class GovIntelPort(Protocol):
    async def check_indicator(
        self,
        indicator: str,
        indicator_type: ThreatIndicatorType,
    ) -> dict[str, Any]:
        ...


class OperatorIntelPort(Protocol):
    async def check_indicator(self, phone_number: str) -> dict[str, Any]:
        ...


class TransactionControlPort(Protocol):
    async def block_transaction(self, operation_id: str, reason: str) -> bool:
        ...

    async def block_resource(
        self,
        resource: str,
        resource_type: str,
        reason: str,
    ) -> bool:
        ...


class NotificationPort(Protocol):
    async def alert_user(self, user_id: str, message: str, channel: str) -> bool:
        ...

    async def send_awareness_hint(self, user_id: str, context: str) -> bool:
        ...
