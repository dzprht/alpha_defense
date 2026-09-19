"""Identity aggregate invariants independent from adapters and HTTP."""

from datetime import timedelta

import pytest
from tests.contract.test_uow_contract import NOW, entity_id

from alpha_defense.domain.identity import (
    ConsentScope,
    ConsentSnapshot,
    ConsentStatus,
    DemoSession,
    PreSession,
    SessionRole,
)


def test_pre_session_can_be_consumed_only_while_available() -> None:
    pre_session = PreSession(
        pre_session_id=entity_id(1),
        token_fingerprint="a" * 64,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )

    consumed = pre_session.consume(entity_id(2), now=NOW)

    assert pre_session.is_available_at(NOW)
    assert consumed.consumed_session_id == entity_id(2)
    assert not consumed.is_available_at(NOW)
    with pytest.raises(ValueError, match="expired or already consumed"):
        consumed.consume(entity_id(3), now=NOW)


def test_consent_and_session_revisions_advance_explicitly() -> None:
    session = DemoSession(
        session_id=entity_id(1),
        user_id=entity_id(2),
        manual_namespace_id=entity_id(3),
        roles=frozenset({SessionRole.DEMO_USER}),
        token_fingerprint="b" * 64,
        consent_revision=0,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=12),
    )
    consent = ConsentSnapshot(
        user_id=session.user_id,
        scope=ConsentScope.PARTICIPATE_IN_RESEARCH,
        status=ConsentStatus.REVOKED,
        revision=0,
        changed_at=NOW,
    )

    advanced = session.advance_consent_revision(expected_revision=0)
    granted = consent.change(
        ConsentStatus.GRANTED,
        revision=advanced.consent_revision,
        changed_at=NOW + timedelta(seconds=1),
    )

    assert advanced.consent_revision == 1
    assert granted.status is ConsentStatus.GRANTED
    assert granted.revision == 1
    with pytest.raises(ValueError, match="stale"):
        session.advance_consent_revision(expected_revision=1)


def test_session_requires_a_server_role() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        DemoSession(
            session_id=entity_id(1),
            user_id=entity_id(2),
            manual_namespace_id=entity_id(3),
            roles=frozenset(),
            token_fingerprint="c" * 64,
            consent_revision=0,
            created_at=NOW,
            expires_at=NOW + timedelta(hours=12),
        )
