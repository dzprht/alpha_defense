"""P22 evidence completeness and server-side transfer decisions."""

from uuid import UUID

import pytest

from alpha_defense.domain.shared import EntityId, Severity
from alpha_defense.domain.transfers import (
    BehaviorFeatures,
    CheckCompleteness,
    ContactEvidenceStatus,
    HistoryStatus,
    RecipientLookupStatus,
    TransferCheckPolicy,
    TransferDecision,
)


def _behavior(*, new: bool | None = False, outlier: bool | None = False) -> BehaviorFeatures:
    return BehaviorFeatures(
        profile_id=EntityId(UUID(int=1)),
        profile_version=1,
        status=HistoryStatus.COMPLETE if new is not None else HistoryStatus.INSUFFICIENT_DATA,
        sample_size=12 if new is not None else 5,
        window_days=90,
        recipient_is_new=new,
        amount_is_outlier=outlier,
        median_amount_minor_x2=200_000 if new is not None else None,
    )


@pytest.fixture
def policy() -> TransferCheckPolicy:
    return TransferCheckPolicy(
        weights={
            "new_recipient": 15,
            "known_recipient_amount_outlier": 30,
            "new_recipient_amount_outlier": 50,
            "active_threat_match": 85,
        },
        low_max=24,
        medium_max=49,
        high_max=79,
        linked_contact_bonus=20,
    )


@pytest.mark.parametrize(
    ("behavior", "lookup", "expected"),
    [
        (_behavior(), RecipientLookupStatus.NO_MATCH, TransferDecision.ALLOW),
        (
            _behavior(new=False, outlier=True),
            RecipientLookupStatus.NO_MATCH,
            TransferDecision.CONFIRM,
        ),
        (_behavior(new=True, outlier=True), RecipientLookupStatus.NO_MATCH, TransferDecision.HOLD),
        (_behavior(), RecipientLookupStatus.MATCH, TransferDecision.DENY),
    ],
)
def test_complete_evidence_maps_all_decisions(
    policy: TransferCheckPolicy,
    behavior: BehaviorFeatures,
    lookup: RecipientLookupStatus,
    expected: TransferDecision,
) -> None:
    outcome = policy.evaluate(
        behavior=behavior,
        recipient_lookup=lookup,
        contact_status=ContactEvidenceStatus.NOT_SELECTED,
        contact_severity=None,
        contact_score=None,
        analysis_pending=False,
    )
    assert outcome.completeness is CheckCompleteness.COMPLETE
    assert outcome.decision is expected


def test_missing_evidence_never_becomes_low_risk_approval(policy: TransferCheckPolicy) -> None:
    unknown = policy.evaluate(
        behavior=_behavior(new=None, outlier=None),
        recipient_lookup=RecipientLookupStatus.UNAVAILABLE,
        contact_status=ContactEvidenceStatus.NOT_SELECTED,
        contact_severity=None,
        contact_score=None,
        analysis_pending=False,
    )
    assert unknown.severity is Severity.UNKNOWN
    assert unknown.completeness is CheckCompleteness.UNAVAILABLE
    assert unknown.decision is TransferDecision.HOLD
    partial = policy.evaluate(
        behavior=_behavior(),
        recipient_lookup=RecipientLookupStatus.UNAVAILABLE,
        contact_status=ContactEvidenceStatus.UNAVAILABLE,
        contact_severity=None,
        contact_score=None,
        analysis_pending=True,
    )
    assert partial.completeness is CheckCompleteness.PARTIAL
    assert partial.decision is TransferDecision.HOLD
    assert "recipient_lookup_unavailable" in partial.reason_codes
    assert "contact_analysis_pending" in partial.reason_codes


def test_linked_contact_can_raise_risk_but_missing_contact_holds(
    policy: TransferCheckPolicy,
) -> None:
    kwargs = dict(
        behavior=_behavior(),
        recipient_lookup=RecipientLookupStatus.NO_MATCH,
        contact_severity=Severity.MEDIUM,
        contact_score=45,
        analysis_pending=False,
    )
    elevated = policy.evaluate(contact_status=ContactEvidenceStatus.COMPLETE, **kwargs)
    assert elevated.severity is Severity.HIGH
    assert elevated.decision is TransferDecision.HOLD
    missing = policy.evaluate(
        contact_status=ContactEvidenceStatus.UNAVAILABLE,
        **{**kwargs, "contact_severity": None, "contact_score": None},
    )
    assert missing.decision is TransferDecision.HOLD
    assert missing.completeness is CheckCompleteness.PARTIAL
