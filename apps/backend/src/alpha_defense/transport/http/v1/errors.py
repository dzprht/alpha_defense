"""Safe mapping from framework/application failures to Problem Details."""

# ruff: noqa: RUF001

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from alpha_defense.application.shared import (
    ActionForbiddenError,
    ActionInProgressError,
    ApplicationError,
    IdempotencyConflictError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    StaleRevisionError,
    ValidationError,
)
from alpha_defense.transport.http.v1.schemas import FieldError, ProblemDetails

PROBLEM_MEDIA_TYPE = "application/problem+json"

_STATUS_BY_ERROR: tuple[tuple[type[ApplicationError], int], ...] = (
    (ValidationError, 422),
    (ResourceNotFoundError, 404),
    (ActionForbiddenError, 403),
    (StaleRevisionError, 409),
    (IdempotencyConflictError, 409),
    (ActionInProgressError, 409),
    (ServiceUnavailableError, 503),
)

_TITLE_BY_STATUS: Mapping[int, str] = {
    400: "Некорректный запрос",
    401: "Требуется сессия",
    403: "Действие недоступно",
    404: "Ресурс не найден",
    409: "Конфликт состояния",
    413: "Слишком большой запрос",
    415: "Неподдерживаемый формат",
    422: "Ошибка проверки данных",
    429: "Слишком много запросов",
    500: "Внутренняя ошибка",
    503: "Сервис временно недоступен",
}


class RequestGuardError(Exception):
    def __init__(self, *, status: int, code: str, detail: str) -> None:
        self.status = status
        self.code = code
        self.detail = detail
        super().__init__(detail)


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(RequestGuardError, request_guard_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)


async def application_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = _as_application_error(exc)
    status = next(
        (
            mapped_status
            for error_type, mapped_status in _STATUS_BY_ERROR
            if isinstance(error, error_type)
        ),
        500,
    )
    field_errors: tuple[FieldError, ...] | None = None
    if isinstance(error, ValidationError) and error.field_errors:
        field_errors = tuple(
            FieldError(field=item.field, code=item.code, message=item.message)
            for item in error.field_errors
        )
    return problem_response(
        request,
        status=status,
        code=error.code,
        detail=error.detail if status < 500 else "Обязательная зависимость временно недоступна.",
        retryable=error.retryable,
        field_errors=field_errors,
    )


async def request_guard_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = _as_guard_error(exc)
    return problem_response(request, status=error.status, code=error.code, detail=error.detail)


async def request_validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = _as_request_validation_error(exc)
    invalid_json = any(item.get("type") == "json_invalid" for item in error.errors())
    if invalid_json:
        return problem_response(
            request,
            status=400,
            code="invalid_json",
            detail="Тело запроса содержит некорректный JSON.",
        )
    fields = tuple(
        FieldError(
            field=_public_location(item.get("loc", ())),
            code=str(item.get("type", "invalid_value"))[:64],
            message="Некорректное значение.",
        )
        for item in error.errors()
    )
    return problem_response(
        request,
        status=422,
        code="validation_failed",
        detail="Проверьте поля запроса.",
        field_errors=fields or None,
    )


async def http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = _as_http_error(exc)
    status = error.status_code
    code = {
        401: "session_required",
        403: "action_forbidden",
        404: "resource_not_found",
        405: "method_not_allowed",
        415: "unsupported_media",
        429: "rate_limited",
    }.get(status, "http_error")
    detail = error.detail if isinstance(error.detail, str) else "Запрос не может быть обработан."
    return problem_response(request, status=status, code=code, detail=detail)


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    del exc
    return problem_response(
        request,
        status=500,
        code="internal_error",
        detail="Запрос не удалось обработать.",
    )


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    detail: str,
    retryable: bool = False,
    field_errors: tuple[FieldError, ...] | None = None,
) -> JSONResponse:
    problem = ProblemDetails(
        type=f"urn:alpha-defense:problem:{code}",
        title=_TITLE_BY_STATUS.get(status, "Ошибка запроса"),
        status=status,
        detail=detail,
        instance=request.url.path,
        code=code,
        request_id=_request_id(request),
        field_errors=field_errors,
        retryable=retryable,
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else "00000000-0000-0000-0000-000000000000"


def _public_location(location: Any) -> str:
    if not isinstance(location, (tuple, list)):
        return "request"
    parts = [str(part) for part in location if part not in {"body", "query", "path", "header"}]
    return ".".join(parts)[:255] or "request"


def _as_application_error(exc: Exception) -> ApplicationError:
    if not isinstance(exc, ApplicationError):
        raise TypeError("expected ApplicationError")
    return exc


def _as_guard_error(exc: Exception) -> RequestGuardError:
    if not isinstance(exc, RequestGuardError):
        raise TypeError("expected RequestGuardError")
    return exc


def _as_request_validation_error(exc: Exception) -> RequestValidationError:
    if not isinstance(exc, RequestValidationError):
        raise TypeError("expected RequestValidationError")
    return exc


def _as_http_error(exc: Exception) -> HTTPException:
    if not isinstance(exc, HTTPException):
        raise TypeError("expected HTTPException")
    return exc
