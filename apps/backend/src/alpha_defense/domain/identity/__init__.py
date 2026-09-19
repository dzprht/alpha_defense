"""Identity domain objects for synthetic sessions and explicit consent."""

from alpha_defense.domain.identity.models import (
    ConsentScope,
    ConsentSnapshot,
    ConsentStatus,
    DemoSession,
    PreSession,
    SessionRole,
    SyntheticUser,
)

__all__ = [
    "ConsentScope",
    "ConsentSnapshot",
    "ConsentStatus",
    "DemoSession",
    "PreSession",
    "SessionRole",
    "SyntheticUser",
]
