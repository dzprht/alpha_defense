"""Pure, deterministic transfer policy over explicitly available synthetic evidence."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_defense.domain.shared import Severity
from alpha_defense.domain.transfers.check import (
    CheckCompleteness,
    ContactEvidenceStatus,
    RecipientLookupStatus,
    TransferDecision,
)
from alpha_defense.domain.transfers.profile import BehaviorFeatures, HistoryStatus


@dataclass(frozen=True, slots=True)
class TransferCheckOutcome:
    severity: Severity
    score: int | None
    completeness: CheckCompleteness
    decision: TransferDecision
    signal_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransferCheckPolicy:
    weights: dict[str, int]
    low_max: int
    medium_max: int
    high_max: int
    linked_contact_bonus: int

    def __post_init__(self) -> None:
        required = {
            "new_recipient",
            "known_recipient_amount_outlier",
            "new_recipient_amount_outlier",
            "active_threat_match",
        }
        if not required <= self.weights.keys():
            raise ValueError("transfer risk policy is missing required weights")
        if not 0 <= self.low_max < self.medium_max < self.high_max < 100:
            raise ValueError("transfer risk thresholds are invalid")
        if not 0 <= self.linked_contact_bonus <= 100:
            raise ValueError("linked contact bonus is invalid")

    def evaluate(
        self,
        *,
        behavior: BehaviorFeatures,
        recipient_lookup: RecipientLookupStatus,
        contact_status: ContactEvidenceStatus,
        contact_severity: Severity | None,
        contact_score: int | None,
        analysis_pending: bool,
    ) -> TransferCheckOutcome:
        reasons: list[str] = []
        signals: list[str] = []
        scores: list[int] = []
        available = False

        if behavior.status is HistoryStatus.COMPLETE:
            available = True
            if behavior.recipient_is_new and behavior.amount_is_outlier:
                signals.append("new_recipient_amount_outlier")
            elif behavior.recipient_is_new:
                signals.append("new_recipient")
            elif behavior.amount_is_outlier:
                signals.append("known_recipient_amount_outlier")
            if signals:
                scores.append(self.weights[signals[-1]])
        else:
            reasons.append("insufficient_history")

        if recipient_lookup is RecipientLookupStatus.MATCH:
            available = True
            signals.append("active_threat_match")
            scores.append(self.weights["active_threat_match"])
        elif recipient_lookup is RecipientLookupStatus.NO_MATCH:
            available = True
        else:
            reasons.append("recipient_lookup_unavailable")

        if contact_status is ContactEvidenceStatus.COMPLETE:
            if contact_severity is None or contact_score is None:
                raise ValueError("complete contact requires severity and score")
            available = True
            if contact_severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL):
                signals.append("linked_contact_risk")
                scores.append(min(100, contact_score + self.linked_contact_bonus))
        elif contact_status is ContactEvidenceStatus.PARTIAL:
            reasons.append("linked_contact_partial")
            if contact_score is not None:
                available = True
                scores.append(contact_score)
        elif contact_status is ContactEvidenceStatus.UNAVAILABLE:
            reasons.append("linked_contact_unavailable")

        if analysis_pending:
            reasons.append("contact_analysis_pending")
        if not available:
            return TransferCheckOutcome(
                severity=Severity.UNKNOWN,
                score=None,
                completeness=CheckCompleteness.UNAVAILABLE,
                decision=TransferDecision.HOLD,
                signal_codes=tuple(signals),
                reason_codes=tuple((*reasons, "risk_unknown")),
            )
        score = max(scores, default=0)
        severity = (
            Severity.LOW
            if score <= self.low_max
            else Severity.MEDIUM
            if score <= self.medium_max
            else Severity.HIGH
            if score <= self.high_max
            else Severity.CRITICAL
        )
        completeness = CheckCompleteness.PARTIAL if reasons else CheckCompleteness.COMPLETE
        if severity is Severity.CRITICAL:
            decision = TransferDecision.DENY
        elif severity is Severity.HIGH or completeness is not CheckCompleteness.COMPLETE:
            decision = TransferDecision.HOLD
        elif severity is Severity.MEDIUM:
            decision = TransferDecision.CONFIRM
        else:
            decision = TransferDecision.ALLOW
        return TransferCheckOutcome(
            severity=severity,
            score=score,
            completeness=completeness,
            decision=decision,
            signal_codes=tuple(signals),
            reason_codes=tuple((*reasons, f"decision_{decision.value}")),
        )
