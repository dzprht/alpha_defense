"""Transport-neutral readiness contract for mandatory local dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """Result of one non-sensitive dependency check."""

    name: str
    ready: bool
    code: str

    def __post_init__(self) -> None:
        if not isinstance(self.ready, bool):
            raise TypeError("ready must be a bool")
        for field_name in ("name", "code"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value or value != value.strip():
                raise ValueError(f"{field_name} must be non-empty and trimmed")


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Aggregate readiness without paths, credentials, or exception messages."""

    checks: tuple[ReadinessCheck, ...]

    def __post_init__(self) -> None:
        if not self.checks:
            raise ValueError("checks must not be empty")
        if any(not isinstance(check, ReadinessCheck) for check in self.checks):
            raise TypeError("checks must contain ReadinessCheck values")
        if len({check.name for check in self.checks}) != len(self.checks):
            raise ValueError("readiness check names must be unique")

    @property
    def ready(self) -> bool:
        return all(check.ready for check in self.checks)


class ReadinessPort(Protocol):
    """Checks dependencies that are mandatory for serving business requests."""

    def check(self) -> ReadinessReport: ...
