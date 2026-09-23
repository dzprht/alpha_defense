"""Application contract and use cases for synthetic identity."""

from alpha_defense.application.identity.accounts import AccountService
from alpha_defense.application.identity.dto import (
    AnonymousSessionView,
    ConsentView,
    SessionBootstrapResult,
    SessionView,
    StartSessionResult,
)
from alpha_defense.application.identity.ports import (
    AccountServicePort,
    AuthenticatedDemoSubject,
    CredentialPort,
    DemoIdentityProviderPort,
    IdentityRepositoryPort,
    IdentityServicePort,
    IdentityUnitOfWorkFactory,
    IdentityUnitOfWorkPort,
    SecurityTokenPort,
)
from alpha_defense.application.identity.service import IdentityService
from alpha_defense.domain.identity import ConsentScope, ConsentStatus

__all__ = [
    "AccountService",
    "AccountServicePort",
    "AnonymousSessionView",
    "AuthenticatedDemoSubject",
    "ConsentScope",
    "ConsentStatus",
    "ConsentView",
    "CredentialPort",
    "DemoIdentityProviderPort",
    "IdentityRepositoryPort",
    "IdentityService",
    "IdentityServicePort",
    "IdentityUnitOfWorkFactory",
    "IdentityUnitOfWorkPort",
    "SecurityTokenPort",
    "SessionBootstrapResult",
    "SessionView",
    "StartSessionResult",
]
