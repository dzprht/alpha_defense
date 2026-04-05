"""Financial awareness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from alpha_protect.application.dto import ProvideAwarenessHintCommand
from alpha_protect.infrastructure.container import UseCaseRegistry
from alpha_protect.presentation.deps import get_use_case_registry
from alpha_protect.presentation.schemas import NotImplementedStubResponse
from alpha_protect.presentation.stubs import build_not_implemented_response

router = APIRouter(prefix="/awareness", tags=["awareness"])


@router.post(
    "/hint",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def provide_awareness_hint(
    command: ProvideAwarenessHintCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.provide_awareness_hint.execute(command)
    return build_not_implemented_response(
        "Awareness hint generation is not implemented yet."
    )
