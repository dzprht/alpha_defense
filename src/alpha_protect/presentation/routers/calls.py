"""Call verification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from alpha_protect.application.dto import VerifyAlfaIdCallCommand
from alpha_protect.infrastructure.container import UseCaseRegistry
from alpha_protect.presentation.deps import get_use_case_registry
from alpha_protect.presentation.schemas import NotImplementedStubResponse
from alpha_protect.presentation.stubs import build_not_implemented_response

router = APIRouter(prefix="/calls", tags=["signals"])


@router.post(
    "/alfa-id/verify",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def verify_alfa_id_call(
    command: VerifyAlfaIdCallCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.verify_alfa_id_call.execute(command)
    return build_not_implemented_response(
        "Alfa ID call verification is not implemented yet."
    )
