"""Types shared by application use cases."""

from alpha_defense.application.shared.actor import ActorContext, ActorRole
from alpha_defense.application.shared.errors import (
    ActionForbiddenError,
    ActionInProgressError,
    ApplicationError,
    ConsentRequiredError,
    FieldViolation,
    IdempotencyConflictError,
    InvalidCredentialsError,
    RateLimitedError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    SessionRequiredError,
    StaleRevisionError,
    ValidationError,
)
from alpha_defense.application.shared.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Page,
    PageRequest,
)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ActionForbiddenError",
    "ActionInProgressError",
    "ActorContext",
    "ActorRole",
    "ApplicationError",
    "ConsentRequiredError",
    "FieldViolation",
    "IdempotencyConflictError",
    "InvalidCredentialsError",
    "Page",
    "PageRequest",
    "RateLimitedError",
    "ResourceNotFoundError",
    "ServiceUnavailableError",
    "SessionRequiredError",
    "StaleRevisionError",
    "ValidationError",
]
