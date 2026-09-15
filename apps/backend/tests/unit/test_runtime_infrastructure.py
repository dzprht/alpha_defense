"""Focused tests for concrete clock, IDs, and canonical fingerprints."""

from datetime import UTC

import pytest

from alpha_defense.application.ports import Clock, IdGenerator
from alpha_defense.infrastructure.runtime import (
    SystemClock,
    UuidGenerator,
    fingerprint_command,
    fingerprint_principal,
)


def test_system_clock_and_uuid_generator_implement_runtime_ports() -> None:
    clock = SystemClock()
    generator = UuidGenerator()

    before = clock.monotonic_ms()
    now = clock.now_utc()
    after = clock.monotonic_ms()

    assert now.tzinfo is UTC
    assert before <= after
    assert generator.new_id() != generator.new_id()
    assert isinstance(clock, Clock)
    assert isinstance(generator, IdGenerator)


def test_command_fingerprint_is_canonical_and_payload_sensitive() -> None:
    first = fingerprint_command({"currency": "RUB", "amount_minor": 100})
    reordered = fingerprint_command({"amount_minor": 100, "currency": "RUB"})
    changed = fingerprint_command({"amount_minor": 101, "currency": "RUB"})

    assert first == reordered
    assert first != changed
    assert len(first) == 64


def test_fingerprints_reject_non_json_or_empty_principals() -> None:
    with pytest.raises(ValueError, match="finite JSON"):
        fingerprint_command({"score": float("nan")})
    with pytest.raises(ValueError, match="at least one"):
        fingerprint_principal([])
