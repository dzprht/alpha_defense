"""Dependency wiring for application use cases."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_protect.application.use_cases import (
    AlertUserUseCase,
    AnalyzeTextSignalUseCase,
    BlockResourceUseCase,
    BlockTransactionUseCase,
    CheckGovIndicatorUseCase,
    CheckOpenBankingOperationUseCase,
    CheckOperatorIndicatorUseCase,
    CheckUrlSignalUseCase,
    DetectBehaviorAnomalyUseCase,
    GetThreatIndicatorUseCase,
    ProvideAwarenessHintUseCase,
    UpsertThreatIndicatorUseCase,
    VerifyAlfaIdCallUseCase,
)
from alpha_protect.infrastructure.clients import (
    StubAlfaIdClient,
    StubGovIntelClient,
    StubNotificationClient,
    StubOpenBankingClient,
    StubOperatorIntelClient,
    StubThreatRegistryClient,
    StubTransactionControlClient,
)


@dataclass(slots=True, frozen=True)
class UseCaseRegistry:
    analyze_text_signal: AnalyzeTextSignalUseCase
    check_url_signal: CheckUrlSignalUseCase
    detect_behavior_anomaly: DetectBehaviorAnomalyUseCase
    verify_alfa_id_call: VerifyAlfaIdCallUseCase
    check_open_banking_operation: CheckOpenBankingOperationUseCase
    check_gov_indicator: CheckGovIndicatorUseCase
    check_operator_indicator: CheckOperatorIndicatorUseCase
    upsert_threat_indicator: UpsertThreatIndicatorUseCase
    get_threat_indicator: GetThreatIndicatorUseCase
    block_transaction: BlockTransactionUseCase
    block_resource: BlockResourceUseCase
    alert_user: AlertUserUseCase
    provide_awareness_hint: ProvideAwarenessHintUseCase


def build_use_case_registry() -> UseCaseRegistry:
    threat_registry = StubThreatRegistryClient()
    alfa_id = StubAlfaIdClient()
    open_banking = StubOpenBankingClient()
    gov_intel = StubGovIntelClient()
    operator_intel = StubOperatorIntelClient()
    transaction_control = StubTransactionControlClient()
    notification = StubNotificationClient()

    return UseCaseRegistry(
        analyze_text_signal=AnalyzeTextSignalUseCase(),
        check_url_signal=CheckUrlSignalUseCase(),
        detect_behavior_anomaly=DetectBehaviorAnomalyUseCase(),
        verify_alfa_id_call=VerifyAlfaIdCallUseCase(alfa_id_port=alfa_id),
        check_open_banking_operation=CheckOpenBankingOperationUseCase(
            open_banking_port=open_banking
        ),
        check_gov_indicator=CheckGovIndicatorUseCase(gov_intel_port=gov_intel),
        check_operator_indicator=CheckOperatorIndicatorUseCase(
            operator_intel_port=operator_intel
        ),
        upsert_threat_indicator=UpsertThreatIndicatorUseCase(
            threat_registry_port=threat_registry
        ),
        get_threat_indicator=GetThreatIndicatorUseCase(
            threat_registry_port=threat_registry
        ),
        block_transaction=BlockTransactionUseCase(
            transaction_control_port=transaction_control
        ),
        block_resource=BlockResourceUseCase(
            transaction_control_port=transaction_control
        ),
        alert_user=AlertUserUseCase(notification_port=notification),
        provide_awareness_hint=ProvideAwarenessHintUseCase(notification_port=notification),
    )
