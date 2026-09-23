"""Transport-neutral errors returned by application use cases."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class FieldViolation:
    """A stable field-level validation error."""

    field: str
    code: str
    message: str

    def __post_init__(self) -> None:
        for field_name in ("field", "code", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value or value != value.strip():
                raise ValueError(f"{field_name} must be non-empty and trimmed")


class ApplicationError(Exception):
    """Base error whose code is mapped by transport without importing transport here."""

    code: ClassVar[str] = "application_error"
    retryable: ClassVar[bool] = False

    def __init__(self, detail: str) -> None:
        if not isinstance(detail, str):
            raise TypeError("detail must be a string")
        if not detail or detail != detail.strip():
            raise ValueError("detail must be non-empty and trimmed")
        self.detail = detail
        super().__init__(detail)


class ValidationError(ApplicationError):
    code = "validation_failed"

    def __init__(
        self,
        detail: str,
        *,
        field_errors: Iterable[FieldViolation] = (),
    ) -> None:
        self.field_errors = tuple(field_errors)
        if any(not isinstance(error, FieldViolation) for error in self.field_errors):
            raise TypeError("field_errors must contain FieldViolation values")
        super().__init__(detail)


class ResourceNotFoundError(ApplicationError):
    code = "resource_not_found"


class ActionForbiddenError(ApplicationError):
    code = "action_forbidden"


class SessionRequiredError(ApplicationError):
    code = "session_required"


class InvalidCredentialsError(ApplicationError):
    code = "invalid_credentials"


class RateLimitedError(ApplicationError):
    code = "rate_limited"
    retryable = True


class ConsentRequiredError(ApplicationError):
    code = "consent_required"


class StaleRevisionError(ApplicationError):
    code = "stale_revision"


class IdempotencyConflictError(ApplicationError):
    code = "idempotency_conflict"


class ActionInProgressError(ApplicationError):
    code = "action_in_progress"
    retryable = True


class ServiceUnavailableError(ApplicationError):
    code = "service_unavailable"
    retryable = True
