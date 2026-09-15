"""Execution provenance shared by domain results."""

from dataclasses import dataclass
from enum import StrEnum


class ExecutionMode(StrEnum):
    """Whether evidence and effects originate from a mock or live adapter."""

    MOCK = "mock"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Versioned origin of a result without provider-specific payloads."""

    execution_mode: ExecutionMode
    provider: str
    provider_version: str
    data_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        for field_name in ("provider", "provider_version", "data_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value or value != value.strip():
                raise ValueError(f"{field_name} must be non-empty and trimmed")
