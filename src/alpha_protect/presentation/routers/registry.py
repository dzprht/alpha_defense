"""Threat registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status

from alpha_protect.application.dto import GetThreatIndicatorQuery, UpsertThreatIndicatorCommand
from alpha_protect.infrastructure.container import UseCaseRegistry
from alpha_protect.presentation.deps import get_use_case_registry
from alpha_protect.presentation.schemas import NotImplementedStubResponse
from alpha_protect.presentation.stubs import build_not_implemented_response

router = APIRouter(prefix="/registry", tags=["registry"])


@router.post(
    "/threats/upsert",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def upsert_threat_indicator(
    command: UpsertThreatIndicatorCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.upsert_threat_indicator.execute(command)
    return build_not_implemented_response("Threat registry upsert is not implemented yet.")


@router.get(
    "/threats/{indicator}",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def get_threat_indicator(
    indicator: str = Path(min_length=1),
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    query = GetThreatIndicatorQuery(indicator=indicator)
    await use_cases.get_threat_indicator.execute(query)
    return build_not_implemented_response("Threat registry lookup is not implemented yet.")
