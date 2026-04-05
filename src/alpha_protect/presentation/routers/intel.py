"""Intelligence providers endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from alpha_protect.application.dto import (
    CheckGovIndicatorCommand,
    CheckOpenBankingOperationCommand,
    CheckOperatorIndicatorCommand,
)
from alpha_protect.infrastructure.container import UseCaseRegistry
from alpha_protect.presentation.deps import get_use_case_registry
from alpha_protect.presentation.schemas import NotImplementedStubResponse
from alpha_protect.presentation.stubs import build_not_implemented_response

router = APIRouter(prefix="/intel", tags=["intel"])


@router.post(
    "/open-banking/check",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def check_open_banking_operation(
    command: CheckOpenBankingOperationCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.check_open_banking_operation.execute(command)
    return build_not_implemented_response(
        "Open banking intelligence check is not implemented yet."
    )


@router.post(
    "/gov/check",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def check_gov_indicator(
    command: CheckGovIndicatorCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.check_gov_indicator.execute(command)
    return build_not_implemented_response(
        "Government intelligence check is not implemented yet."
    )


@router.post(
    "/operator/check",
    response_model=NotImplementedStubResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def check_operator_indicator(
    command: CheckOperatorIndicatorCommand,
    use_cases: UseCaseRegistry = Depends(get_use_case_registry),
) -> NotImplementedStubResponse:
    await use_cases.check_operator_indicator.execute(command)
    return build_not_implemented_response(
        "Mobile operator intelligence check is not implemented yet."
    )
