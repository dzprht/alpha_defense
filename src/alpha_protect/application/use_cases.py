"""Application use cases. Business logic is intentionally not implemented yet."""

from __future__ import annotations

from alpha_protect.application.dto import (
    AlertUserCommand,
    AnalyzeTextSignalCommand,
    BlockResourceCommand,
    BlockTransactionCommand,
    CheckGovIndicatorCommand,
    CheckOpenBankingOperationCommand,
    CheckOperatorIndicatorCommand,
    CheckUrlSignalCommand,
    DetectBehaviorAnomalyCommand,
    GetThreatIndicatorQuery,
    ProvideAwarenessHintCommand,
    UpsertThreatIndicatorCommand,
    VerifyAlfaIdCallCommand,
)
from alpha_protect.domain.ports import (
    AlfaIdPort,
    GovIntelPort,
    NotificationPort,
    OpenBankingPort,
    OperatorIntelPort,
    ThreatRegistryPort,
    TransactionControlPort,
)


class AnalyzeTextSignalUseCase:
    async def execute(self, command: AnalyzeTextSignalCommand) -> None:
        pass


class CheckUrlSignalUseCase:
    async def execute(self, command: CheckUrlSignalCommand) -> None:
        pass


class DetectBehaviorAnomalyUseCase:
    async def execute(self, command: DetectBehaviorAnomalyCommand) -> None:
        pass


class VerifyAlfaIdCallUseCase:
    def __init__(self, alfa_id_port: AlfaIdPort) -> None:
        self._alfa_id_port = alfa_id_port

    async def execute(self, command: VerifyAlfaIdCallCommand) -> None:
        pass


class CheckOpenBankingOperationUseCase:
    def __init__(self, open_banking_port: OpenBankingPort) -> None:
        self._open_banking_port = open_banking_port

    async def execute(self, command: CheckOpenBankingOperationCommand) -> None:
        pass


class CheckGovIndicatorUseCase:
    def __init__(self, gov_intel_port: GovIntelPort) -> None:
        self._gov_intel_port = gov_intel_port

    async def execute(self, command: CheckGovIndicatorCommand) -> None:
        pass


class CheckOperatorIndicatorUseCase:
    def __init__(self, operator_intel_port: OperatorIntelPort) -> None:
        self._operator_intel_port = operator_intel_port

    async def execute(self, command: CheckOperatorIndicatorCommand) -> None:
        pass


class UpsertThreatIndicatorUseCase:
    def __init__(self, threat_registry_port: ThreatRegistryPort) -> None:
        self._threat_registry_port = threat_registry_port

    async def execute(self, command: UpsertThreatIndicatorCommand) -> None:
        pass


class GetThreatIndicatorUseCase:
    def __init__(self, threat_registry_port: ThreatRegistryPort) -> None:
        self._threat_registry_port = threat_registry_port

    async def execute(self, query: GetThreatIndicatorQuery) -> None:
        pass


class BlockTransactionUseCase:
    def __init__(self, transaction_control_port: TransactionControlPort) -> None:
        self._transaction_control_port = transaction_control_port

    async def execute(self, command: BlockTransactionCommand) -> None:
        pass


class BlockResourceUseCase:
    def __init__(self, transaction_control_port: TransactionControlPort) -> None:
        self._transaction_control_port = transaction_control_port

    async def execute(self, command: BlockResourceCommand) -> None:
        pass


class AlertUserUseCase:
    def __init__(self, notification_port: NotificationPort) -> None:
        self._notification_port = notification_port

    async def execute(self, command: AlertUserCommand) -> None:
        pass


class ProvideAwarenessHintUseCase:
    def __init__(self, notification_port: NotificationPort) -> None:
        self._notification_port = notification_port

    async def execute(self, command: ProvideAwarenessHintCommand) -> None:
        pass
