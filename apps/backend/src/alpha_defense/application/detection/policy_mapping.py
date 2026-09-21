"""Map validated content policy snapshots into domain policy objects."""

from alpha_defense.application.ports import PolicySnapshot
from alpha_defense.domain.detection import (
    RiskPolicy,
    RiskThresholds,
    SignalPolicyDefinition,
)


def risk_policy_from_snapshot(snapshot: PolicySnapshot) -> RiskPolicy:
    return RiskPolicy(
        policy_version=snapshot.policy_version,
        score_kind=snapshot.score_kind,
        thresholds=RiskThresholds(
            low_max=snapshot.thresholds.low_max,
            medium_max=snapshot.thresholds.medium_max,
            high_max=snapshot.thresholds.high_max,
            critical_max=snapshot.thresholds.critical_max,
        ),
        signals=tuple(
            SignalPolicyDefinition(
                code=item.code,
                group=item.group,
                base_score=item.base_score,
            )
            for item in snapshot.signals
        ),
        urgency_with_other_signal=snapshot.urgency_with_other_signal,
        linked_contact=snapshot.linked_contact,
        max_score=snapshot.max_score,
    )
