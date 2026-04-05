"""Stub infrastructure adapters for external integrations."""

from __future__ import annotations

from typing import Any

from alpha_protect.domain.entities import ThreatIndicator, ThreatIndicatorType
from alpha_protect.domain.ports import (
    AlfaIdPort,
    GovIntelPort,
    NotificationPort,
    OpenBankingPort,
    OperatorIntelPort,
    ThreatRegistryPort,
    TransactionControlPort,
)


class StubThreatRegistryClient(ThreatRegistryPort):
    async def upsert(self, indicator: ThreatIndicator) -> None:
        pass

    async def get(self, indicator: str) -> ThreatIndicator | None:
        pass


class StubAlfaIdClient(AlfaIdPort):
    async def verify_call(
        self,
        phone_number: str,
        claimed_source: str,
        call_id: str | None = None,
    ) -> bool:
        pass


class StubOpenBankingClient(OpenBankingPort):
    async def check_operation(
        self,
        operation_id: str,
        user_id: str,
        amount: float,
    ) -> dict[str, Any]:
        pass


class StubGovIntelClient(GovIntelPort):
    async def check_indicator(
        self,
        indicator: str,
        indicator_type: ThreatIndicatorType,
    ) -> dict[str, Any]:
        pass


class StubOperatorIntelClient(OperatorIntelPort):
    async def check_indicator(self, phone_number: str) -> dict[str, Any]:
        pass


class StubTransactionControlClient(TransactionControlPort):
    async def block_transaction(self, operation_id: str, reason: str) -> bool:
        pass

    async def block_resource(
        self,
        resource: str,
        resource_type: str,
        reason: str,
    ) -> bool:
        pass


class StubNotificationClient(NotificationPort):
    async def alert_user(self, user_id: str, message: str, channel: str) -> bool:
        pass

    async def send_awareness_hint(self, user_id: str, context: str) -> bool:
        pass
