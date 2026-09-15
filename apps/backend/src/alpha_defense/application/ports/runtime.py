"""Runtime capabilities injected into application use cases."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from alpha_defense.domain.shared import EntityId


@runtime_checkable
class Clock(Protocol):
    """Provide UTC wall time and monotonic elapsed time without globals in domain code."""

    def now_utc(self) -> datetime:
        """Return an aware UTC datetime."""

    def monotonic_ms(self) -> int:
        """Return monotonic milliseconds for durations, not persisted timestamps."""


@runtime_checkable
class IdGenerator(Protocol):
    """Generate runtime entity identifiers outside domain objects."""

    def new_id(self) -> EntityId:
        """Return a fresh runtime ID."""
