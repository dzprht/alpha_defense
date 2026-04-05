"""Application-level DTOs used by API and use cases."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from alpha_protect.domain.entities import ThreatIndicatorType


class CommandModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResourceType(str, Enum):
    URL = "url"
    DOMAIN = "domain"
    PHONE = "phone"
    WALLET = "wallet"
    IP = "ip"


class AlertChannel(str, Enum):
    PUSH = "push"
    SMS = "sms"
    CALL = "call"
    EMAIL = "email"


class AnalyzeTextSignalCommand(CommandModel):
    text: str = Field(min_length=1)
    channel: str = Field(default="sms", min_length=1)
    user_id: str | None = Field(default=None, min_length=1)


class CheckUrlSignalCommand(CommandModel):
    url: HttpUrl
    source: str = Field(default="unknown", min_length=1)


class DetectBehaviorAnomalyCommand(CommandModel):
    user_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    amount: float = Field(gt=0)


class VerifyAlfaIdCallCommand(CommandModel):
    phone_number: str = Field(min_length=5)
    claimed_source: str = Field(min_length=1)
    call_id: str | None = Field(default=None, min_length=1)


class CheckOpenBankingOperationCommand(CommandModel):
    operation_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    amount: float = Field(gt=0)


class CheckGovIndicatorCommand(CommandModel):
    indicator: str = Field(min_length=1)
    indicator_type: ThreatIndicatorType


class CheckOperatorIndicatorCommand(CommandModel):
    phone_number: str = Field(min_length=5)


class UpsertThreatIndicatorCommand(CommandModel):
    indicator: str = Field(min_length=1)
    indicator_type: ThreatIndicatorType
    source: str = Field(min_length=1)


class GetThreatIndicatorQuery(CommandModel):
    indicator: str = Field(min_length=1)


class BlockTransactionCommand(CommandModel):
    operation_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class BlockResourceCommand(CommandModel):
    resource: str = Field(min_length=1)
    resource_type: ResourceType
    reason: str = Field(min_length=1)


class AlertUserCommand(CommandModel):
    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    channel: AlertChannel


class ProvideAwarenessHintCommand(CommandModel):
    user_id: str = Field(min_length=1)
    context: str = Field(min_length=1)
