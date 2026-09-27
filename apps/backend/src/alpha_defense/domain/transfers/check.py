"""Immutable transfer-check snapshots and fail-closed freshness rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from alpha_defense.domain.shared import EntityId, Severity
from alpha_defense.domain.transfers.intent import IntentStatus, TransferIntent, _require_utc
from alpha_defense.domain.transfers.profile import HistoryStatus

TRANSFER_POLICY_VERSION = "transfer-risk-v1"
CHECK_TTL = timedelta(seconds=120)
_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class CheckCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class TransferDecision(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    HOLD = "hold"
    DENY = "deny"


class RecipientLookupStatus(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"


class ContactEvidenceStatus(StrEnum):
    NOT_SELECTED = "not_selected"
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class TransferCheck:
    check_id: EntityId
    intent_id: EntityId
    owner_id: EntityId
    namespace_id: EntityId
    intent_revision: int
    intent_fingerprint: str
    profile_id: EntityId
    history_version: int
    consent_revision: int
    ingress_epoch: int
    linked_incident_id: EntityId | None
    context_version: int | None
    contact_assessment_id: EntityId | None
    model_version: str | None
    policy_version: str
    catalog_policy_version: str
    registry_snapshot_id: EntityId | None
    registry_version: str | None
    registry_valid_until: datetime | None
    behavior_status: HistoryStatus
    sample_size: int
    recipient_is_new: bool | None
    amount_is_outlier: bool | None
    recipient_lookup: RecipientLookupStatus
    contact_status: ContactEvidenceStatus
    severity: Severity
    score: int | None
    completeness: CheckCompleteness
    decision: TransferDecision
    signal_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    checked_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("check_id", "intent_id", "owner_id", "namespace_id", "profile_id"):
            if not isinstance(getattr(self, name), EntityId):
                raise TypeError(f"{name} must be EntityId")
        for name in ("linked_incident_id", "contact_assessment_id", "registry_snapshot_id"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, EntityId):
                raise TypeError(f"{name} must be EntityId or None")
        for name in ("intent_revision", "history_version"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be positive")
        if type(self.consent_revision) is not int or self.consent_revision < 0:
            raise ValueError("consent_revision must be non-negative")
        if type(self.ingress_epoch) is not int or self.ingress_epoch < 0:
            raise ValueError("ingress_epoch must be non-negative")
        if self.context_version is not None and (
            type(self.context_version) is not int or self.context_version < 1
        ):
            raise ValueError("context_version must be positive or None")
        if (self.linked_incident_id is None) != (self.context_version is None):
            raise ValueError("linked incident and context version must be paired")
        if (
            self.linked_incident_id is None
            and self.contact_status is not ContactEvidenceStatus.NOT_SELECTED
        ):
            raise ValueError("unselected contact must be not applicable")
        if (
            self.linked_incident_id is not None
            and self.contact_status is ContactEvidenceStatus.NOT_SELECTED
        ):
            raise ValueError("selected contact requires a status")
        if self.contact_assessment_id is not None and self.linked_incident_id is None:
            raise ValueError("contact assessment requires a linked incident")
        if not isinstance(self.intent_fingerprint, str) or not _DIGEST.fullmatch(
            self.intent_fingerprint
        ):
            raise ValueError("intent_fingerprint must be SHA-256")
        for name in ("policy_version", "catalog_policy_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 128:
                raise ValueError(f"{name} must be a bounded version")
        for name in ("model_version", "registry_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value or len(value) > 128):
                raise ValueError(f"{name} must be a bounded version or None")
        if (self.registry_snapshot_id is None) != (self.registry_version is None):
            raise ValueError("registry ID and version must be paired")
        if self.registry_valid_until is not None:
            _require_utc(self.registry_valid_until, "registry_valid_until")
        if not isinstance(self.behavior_status, HistoryStatus):
            raise TypeError("behavior_status must be HistoryStatus")
        if type(self.sample_size) is not int or self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")
        if self.behavior_status is HistoryStatus.INSUFFICIENT_DATA and (
            self.recipient_is_new is not None or self.amount_is_outlier is not None
        ):
            raise ValueError("insufficient history cannot supply behavior flags")
        if self.behavior_status is HistoryStatus.COMPLETE and (
            type(self.recipient_is_new) is not bool or type(self.amount_is_outlier) is not bool
        ):
            raise ValueError("complete history requires behavior flags")
        if not isinstance(self.recipient_lookup, RecipientLookupStatus):
            raise TypeError("recipient_lookup must be RecipientLookupStatus")
        if not isinstance(self.contact_status, ContactEvidenceStatus):
            raise TypeError("contact_status must be ContactEvidenceStatus")
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be Severity")
        if not isinstance(self.completeness, CheckCompleteness):
            raise TypeError("completeness must be CheckCompleteness")
        if not isinstance(self.decision, TransferDecision):
            raise TypeError("decision must be TransferDecision")
        if (self.severity is Severity.UNKNOWN) != (self.score is None):
            raise ValueError("unknown severity requires absent score")
        if self.score is not None and (type(self.score) is not int or not 0 <= self.score <= 100):
            raise ValueError("score must be an integer from 0 to 100")
        if self.completeness is not CheckCompleteness.COMPLETE and self.decision in (
            TransferDecision.ALLOW,
            TransferDecision.CONFIRM,
        ):
            raise ValueError("incomplete check cannot permit a transfer")
        if self.severity is Severity.UNKNOWN and self.decision is not TransferDecision.HOLD:
            raise ValueError("unknown risk must hold")
        for name in ("signal_codes", "reason_codes"):
            codes = getattr(self, name)
            if (
                not isinstance(codes, tuple)
                or len(codes) != len(set(codes))
                or any(not isinstance(code, str) or not _CODE.fullmatch(code) for code in codes)
            ):
                raise ValueError(f"{name} must contain unique stable codes")
        _require_utc(self.checked_at, "checked_at")
        _require_utc(self.expires_at, "expires_at")
        if not self.checked_at < self.expires_at <= self.checked_at + CHECK_TTL:
            raise ValueError("check expiry must be within 120 seconds")
        if self.registry_valid_until is not None and self.expires_at > self.registry_valid_until:
            raise ValueError("check cannot outlive its registry snapshot")

    def stale_reasons(
        self,
        *,
        now: datetime,
        intent: TransferIntent,
        history_version: int,
        consent_revision: int,
        ingress_epoch: int,
        analysis_pending: bool,
        context_version: int | None,
        contact_assessment_id: EntityId | None,
        registry_snapshot_id: EntityId | None,
        catalog_policy_version: str,
        latest_check_id: EntityId | None,
    ) -> tuple[str, ...]:
        """Compare current state with the immutable evidence snapshot."""

        _require_utc(now, "now")
        reasons: list[str] = []
        if now >= self.expires_at:
            reasons.append("check_expired")
        if latest_check_id != self.check_id:
            reasons.append("check_superseded")
        if (
            intent.intent_id != self.intent_id
            or intent.owner_id != self.owner_id
            or intent.namespace_id != self.namespace_id
            or intent.revision != self.intent_revision
            or intent.fingerprint != self.intent_fingerprint
            or intent.status is not IntentStatus.CHECKED
        ):
            reasons.append("intent_changed")
        if history_version != self.history_version:
            reasons.append("history_changed")
        if consent_revision != self.consent_revision:
            reasons.append("consent_changed")
        if ingress_epoch != self.ingress_epoch or analysis_pending:
            reasons.append("contact_context_changed")
        if (
            context_version != self.context_version
            or contact_assessment_id != self.contact_assessment_id
        ):
            reasons.append("linked_contact_changed")
        if registry_snapshot_id != self.registry_snapshot_id:
            reasons.append("registry_changed")
        if (
            self.policy_version != TRANSFER_POLICY_VERSION
            or catalog_policy_version != self.catalog_policy_version
        ):
            reasons.append("policy_changed")
        return tuple(reasons)
