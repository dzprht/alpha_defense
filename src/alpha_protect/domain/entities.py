"""Domain entities for the anti-fraud context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SignalType(str, Enum):
    TEXT = "text"
    URL = "url"
    BEHAVIOR = "behavior"
    CALL = "call"


class ThreatIndicatorType(str, Enum):
    PHONE = "phone"
    URL = "url"
    WALLET = "wallet"
    IP = "ip"
    DOMAIN = "domain"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MitigationActionType(str, Enum):
    BLOCK_TRANSACTION = "block_transaction"
    BLOCK_RESOURCE = "block_resource"
    ALERT_USER = "alert_user"
    AWARENESS_HINT = "awareness_hint"


@dataclass(slots=True, frozen=True)
class FraudSignal:
    signal_type: SignalType
    source: str
    payload: dict[str, Any]
    received_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class ThreatIndicator:
    indicator: str
    indicator_type: ThreatIndicatorType
    source: str
    listed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class Incident:
    incident_id: str
    user_id: str
    signals: tuple[FraudSignal, ...]
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class RiskAssessment:
    incident_id: str
    risk_score: float
    risk_level: RiskLevel
    reasons: tuple[str, ...]
    assessed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True, frozen=True)
class MitigationAction:
    action_type: MitigationActionType
    target: str
    rationale: str
    created_at: datetime = field(default_factory=utc_now)
