"""System endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from alpha_protect.presentation.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health_check() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=HealthResponse, summary="Readiness probe")
async def readiness_check() -> HealthResponse:
    return HealthResponse()
