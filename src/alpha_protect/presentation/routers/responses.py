"""Mitigation response endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from alpha_protect.application.dto import (
    AlertUserCommand,
    BlockResourceCommand,
    BlockTransactionCommand,
)
from alpha_protect.infrastructure.container import UseCaseRegistry
from alpha_protect.presentation.deps import get_use_case_registry
from alpha_protect.presentation.schemas import NotImplementedStubResponse
from alpha_protect.presentation.stubs import build_not_implemented_response

router = APIRouter(prefix="/responses", tags=["responses"])


@router.post(
    "/transaction/block",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def block_transaction(
    command: BlockTransactionCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.block_transaction.execute(command)
    return build_not_implemented_response("Transaction blocking is not implemented yet.")


@router.post(
    "/resource/block",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def block_resource(
    command: BlockResourceCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.block_resource.execute(command)
    return build_not_implemented_response("Resource blocking is not implemented yet.")


@router.post(
    "/user/alert",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def alert_user(
    command: AlertUserCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.alert_user.execute(command)
    return build_not_implemented_response("User alerting is not implemented yet.")
