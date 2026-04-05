"""Signal analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from alpha_protect.application.dto import (
    AnalyzeTextSignalCommand,
    CheckUrlSignalCommand,
    DetectBehaviorAnomalyCommand,
)
from alpha_protect.infrastructure.container import UseCaseRegistry
from alpha_protect.presentation.deps import get_use_case_registry
from alpha_protect.presentation.schemas import NotImplementedStubResponse
from alpha_protect.presentation.stubs import build_not_implemented_response

router = APIRouter(prefix="/signals", tags=["signals"])


@router.post(
    "/text/analyze",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def analyze_text_signal(
    command: AnalyzeTextSignalCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.analyze_text_signal.execute(command)
    return build_not_implemented_response("NLP signal analysis is not implemented yet.")


@router.post(
    "/url/check",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def check_url_signal(
    command: CheckUrlSignalCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.check_url_signal.execute(command)
    return build_not_implemented_response("URL and phishing analysis is not implemented yet.")


@router.post(
    "/behavior/anomaly",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def detect_behavior_anomaly(
    command: DetectBehaviorAnomalyCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.detect_behavior_anomaly.execute(command)
    return build_not_implemented_response(
        "Behavioral anomaly analysis is not implemented yet."
    )
