"""Production runtime values injected through application ports."""

from datetime import UTC, datetime
from time import monotonic_ns
from uuid import uuid4

from alpha_defense.domain.shared import EntityId


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def monotonic_ms(self) -> int:
        return monotonic_ns() // 1_000_000


class UuidGenerator:
    def new_id(self) -> EntityId:
        return EntityId(uuid4())
