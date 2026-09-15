"""Identifiers used at domain boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self
from uuid import UUID


@dataclass(frozen=True, slots=True, order=True)
class EntityId:
    """A validated runtime UUID with canonical string rendering."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("EntityId.value must be a UUID")

    @classmethod
    def from_string(cls, raw_value: str) -> Self:
        if not isinstance(raw_value, str):
            raise TypeError("EntityId input must be a string")
        try:
            parsed = UUID(raw_value)
        except (AttributeError, ValueError) as exc:
            raise ValueError("EntityId input must be a valid UUID string") from exc
        return cls(parsed)

    def __str__(self) -> str:
        return str(self.value)
