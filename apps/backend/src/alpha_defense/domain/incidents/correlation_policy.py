"""Deterministic preliminary incident correlation without time-only merging."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from alpha_defense.domain.shared import EntityId


class CorrelationKeyKind(StrEnum):
    CONVERSATION = "conversation"
    CALL = "call"
    INDICATOR = "indicator"


class CorrelationReason(StrEnum):
    NEW_INCIDENT = "new_incident"
    CONVERSATION = "conversation"
    CALL = "call"
    INDICATOR = "indicator"


@dataclass(frozen=True, slots=True, order=True)
class CorrelationKey:
    kind: CorrelationKeyKind
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CorrelationKeyKind):
            raise TypeError("kind must be a CorrelationKeyKind")
        if not isinstance(self.value, str) or not self.value or len(self.value) > 4096:
            raise ValueError("correlation key must contain 1..4096 characters")


class CorrelationCandidate(Protocol):
    @property
    def incident_id(self) -> EntityId: ...

    @property
    def observation_links(self) -> tuple[object, ...]: ...


@dataclass(frozen=True, slots=True)
class CorrelationMatch:
    incident_id: EntityId
    reason: CorrelationReason
    key: CorrelationKey


class PreliminaryCorrelationPolicy:
    """Prefer explicit conversation/call identity, then a normalized indicator."""

    def choose(
        self,
        *,
        candidates: tuple[CorrelationCandidate, ...],
        available_keys: tuple[CorrelationKey, ...],
    ) -> CorrelationMatch | None:
        priorities = (
            (CorrelationKeyKind.CONVERSATION, CorrelationReason.CONVERSATION),
            (CorrelationKeyKind.CALL, CorrelationReason.CALL),
            (CorrelationKeyKind.INDICATOR, CorrelationReason.INDICATOR),
        )
        for key_kind, reason in priorities:
            requested = tuple(key for key in available_keys if key.kind is key_kind)
            if not requested:
                continue
            for candidate in reversed(candidates):
                candidate_keys = _candidate_keys(candidate)
                for key in requested:
                    if key in candidate_keys:
                        return CorrelationMatch(
                            incident_id=candidate.incident_id,
                            reason=reason,
                            key=key,
                        )
        return None


def _candidate_keys(candidate: CorrelationCandidate) -> frozenset[CorrelationKey]:
    keys: set[CorrelationKey] = set()
    for link in candidate.observation_links:
        available = getattr(link, "available_keys", None)
        if isinstance(available, tuple):
            keys.update(key for key in available if isinstance(key, CorrelationKey))
    return frozenset(keys)
