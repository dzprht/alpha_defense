"""Unit tests for common application contracts."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from alpha_defense.application.ports import Clock, IdGenerator
from alpha_defense.application.shared import (
    ActionInProgressError,
    ActorContext,
    ActorRole,
    FieldViolation,
    Page,
    PageRequest,
    ValidationError,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode


class FrozenClock:
    def __init__(self, value: datetime, elapsed_ms: int) -> None:
        self._value = value
        self._elapsed_ms = elapsed_ms

    def now_utc(self) -> datetime:
        return self._value

    def monotonic_ms(self) -> int:
        return self._elapsed_ms


class FixedIdGenerator:
    def __init__(self, value: EntityId) -> None:
        self._value = value

    def new_id(self) -> EntityId:
        return self._value


def _entity_id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


def test_runtime_time_and_ids_are_obtained_from_injected_ports() -> None:
    now = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
    expected_id = _entity_id(1)
    clock: Clock = FrozenClock(now, elapsed_ms=1234)
    id_generator: IdGenerator = FixedIdGenerator(expected_id)

    assert clock.now_utc() == now
    assert clock.monotonic_ms() == 1234
    assert id_generator.new_id() == expected_id
    assert isinstance(clock, Clock)
    assert isinstance(id_generator, IdGenerator)


def test_actor_context_contains_only_server_created_identity_values() -> None:
    actor = ActorContext(
        user_id=_entity_id(1),
        session_id=_entity_id(2),
        namespace_id=_entity_id(3),
        roles=frozenset({ActorRole.DEMO_USER}),
        consent_revision=0,
        execution_mode=ExecutionMode.MOCK,
    )

    assert actor.has_role(ActorRole.DEMO_USER)
    assert not actor.has_role(ActorRole.RESEARCHER)


@pytest.mark.parametrize("consent_revision", [True, -1])
def test_actor_context_rejects_invalid_consent_revision(consent_revision: int) -> None:
    expected_error = TypeError if consent_revision is True else ValueError
    with pytest.raises(expected_error):
        ActorContext(
            user_id=_entity_id(1),
            session_id=_entity_id(2),
            namespace_id=_entity_id(3),
            roles=frozenset({ActorRole.DEMO_USER}),
            consent_revision=consent_revision,
            execution_mode=ExecutionMode.MOCK,
        )


@pytest.mark.parametrize("limit", [0, 101])
def test_page_request_rejects_out_of_range_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        PageRequest(limit=limit)


def test_page_uses_immutable_items_and_opaque_cursor() -> None:
    page = Page(items=("first", "second"), next_cursor="opaque-token")

    assert page.items == ("first", "second")
    assert page.next_cursor == "opaque-token"


def test_application_errors_expose_stable_transport_neutral_data() -> None:
    violation = FieldViolation(field="amount_minor", code="not_integer", message="Use minor units")
    error = ValidationError("Command validation failed", field_errors=[violation])
    in_progress = ActionInProgressError("The command is already in progress")

    assert error.code == "validation_failed"
    assert error.field_errors == (violation,)
    assert not error.retryable
    assert in_progress.code == "action_in_progress"
    assert in_progress.retryable
