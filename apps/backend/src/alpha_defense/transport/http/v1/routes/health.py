"""Liveness and readiness endpoints."""

from typing import cast

from fastapi import APIRouter, Request, Response

from alpha_defense.application.ports import ReadinessPort
from alpha_defense.transport.http.v1.errors import problem_response
from alpha_defense.transport.http.v1.schemas import (
    DependencyStatus,
    LivenessResponse,
    ProblemDetails,
    ReadinessResponse,
)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", operation_id="get_liveness", response_model=LivenessResponse)
async def liveness(request: Request) -> LivenessResponse:
    return LivenessResponse(request_id=request.state.request_id)


@router.get(
    "/ready",
    operation_id="get_readiness",
    response_model=ReadinessResponse,
    responses={
        503: {
            "model": ProblemDetails,
            "description": "Mandatory dependency is unavailable",
            "content": {"application/problem+json": {}},
        }
    },
)
async def readiness(request: Request) -> ReadinessResponse | Response:
    checker = _readiness_checker(request)
    report = checker.check()
    if not report.ready:
        return problem_response(
            request,
            status=503,
            code="service_unavailable",
            detail="Обязательная зависимость приложения пока недоступна.",
            retryable=True,
        )
    return ReadinessResponse(
        request_id=request.state.request_id,
        checks=tuple(DependencyStatus(name=check.name) for check in report.checks),
    )


def _readiness_checker(request: Request) -> ReadinessPort:
    checker = getattr(request.app.state, "readiness", None)
    if checker is None or not hasattr(checker, "check"):
        raise RuntimeError("readiness dependency was not configured")
    return cast(ReadinessPort, checker)
