"""Identity domain objects for synthetic sessions and explicit consent."""

from alpha_defense.domain.identity.models import (
    Account,
    AccountStatus,
    ConsentScope,
    ConsentSnapshot,
    ConsentStatus,
    DemoSession,
    LoginThrottle,
    PreSession,
    SessionAuthKind,
    SessionRole,
    SyntheticUser,
    normalize_login,
)

__all__ = [
    "Account",
    "AccountStatus",
    "ConsentScope",
    "ConsentSnapshot",
    "ConsentStatus",
    "DemoSession",
    "LoginThrottle",
    "PreSession",
    "SessionAuthKind",
    "SessionRole",
    "SyntheticUser",
    "normalize_login",
]
