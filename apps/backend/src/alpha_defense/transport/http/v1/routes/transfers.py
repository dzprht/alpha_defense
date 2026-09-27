"""Owner-scoped synthetic finance profiles; transfer UI arrives in P24."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from alpha_defense.application.shared import ActorContext
from alpha_defense.application.transfers import Currency, EntityId, Money
from alpha_defense.transport.http.v1.dependencies import (
    complete_transfer_service,
    current_actor,
    financial_profiles_service,
    transfer_checks_service,
    transfer_intents_service,
)
from alpha_defense.transport.http.v1.guards import require_csrf, require_idempotency_key
from alpha_defense.transport.http.v1.schemas.transfers import (
    CancelTransferBody,
    CreateProfileBody,
    CreateTransferCheckBody,
    CreateTransferIntentBody,
    ExecuteTransferBody,
    FinancialProfileResponse,
    FinancialProfilesResponse,
    ProfileTemplateResponse,
    ProfileTemplatesResponse,
    ReviseTransferIntentBody,
    TransferCheckResponse,
    TransferChecksResponse,
    TransferCompletionResponse,
    TransferIntentResponse,
    TransferIntentsResponse,
)

router = APIRouter(tags=["transfers"])

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {
        "description": "Problem Details",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        },
    }
    for code in (400, 401, 403, 404, 409, 422, 503)
}


@router.get(
    "/profile-templates",
    operation_id="list_profile_templates",
    response_model=ProfileTemplatesResponse,
    responses=PROBLEM_RESPONSES,
)
def list_profile_templates(
    request: Request, actor: Annotated[ActorContext, Depends(current_actor)]
) -> ProfileTemplatesResponse:
    templates = financial_profiles_service(request).list_templates()
    return ProfileTemplatesResponse(
        items=[ProfileTemplateResponse.from_template(x) for x in templates]
    )


@router.post(
    "/profiles",
    operation_id="create_financial_profile",
    status_code=status.HTTP_201_CREATED,
    response_model=FinancialProfileResponse,
    responses=PROBLEM_RESPONSES,
)
def create_financial_profile(
    payload: CreateProfileBody,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> FinancialProfileResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    profile = financial_profiles_service(request).create_from_template(
        actor=actor, template_code=payload.template_code, idempotency_key=key
    )
    return FinancialProfileResponse.from_profile(profile)


@router.get(
    "/profiles",
    operation_id="list_financial_profiles",
    response_model=FinancialProfilesResponse,
    responses=PROBLEM_RESPONSES,
)
def list_financial_profiles(
    request: Request, actor: Annotated[ActorContext, Depends(current_actor)]
) -> FinancialProfilesResponse:
    profiles = financial_profiles_service(request).list_owned(actor=actor)
    return FinancialProfilesResponse(
        items=[FinancialProfileResponse.from_profile(x) for x in profiles]
    )


@router.get(
    "/profiles/{profile_id}",
    operation_id="get_financial_profile",
    response_model=FinancialProfileResponse,
    responses=PROBLEM_RESPONSES,
)
def get_financial_profile(
    profile_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> FinancialProfileResponse:
    profile = financial_profiles_service(request).get(actor=actor, profile_id=EntityId(profile_id))
    return FinancialProfileResponse.from_profile(profile)


@router.post(
    "/transfer-intents",
    operation_id="create_transfer_intent",
    status_code=status.HTTP_201_CREATED,
    response_model=TransferIntentResponse,
    responses=PROBLEM_RESPONSES,
)
def create_transfer_intent(
    payload: CreateTransferIntentBody,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> TransferIntentResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    intent = transfer_intents_service(request).create(
        actor=actor,
        profile_id=EntityId(payload.profile_id),
        amount=Money(payload.amount_minor, Currency.RUB),
        recipient_code=payload.recipient_code,
        idempotency_key=key,
    )
    return TransferIntentResponse.from_intent(intent)


@router.get(
    "/transfer-intents",
    operation_id="list_transfer_intents",
    response_model=TransferIntentsResponse,
    responses=PROBLEM_RESPONSES,
)
def list_transfer_intents(
    request: Request, actor: Annotated[ActorContext, Depends(current_actor)]
) -> TransferIntentsResponse:
    intents = transfer_intents_service(request).list_owned(actor=actor)
    return TransferIntentsResponse(items=[TransferIntentResponse.from_intent(x) for x in intents])


@router.get(
    "/transfer-intents/{intent_id}",
    operation_id="get_transfer_intent",
    response_model=TransferIntentResponse,
    responses=PROBLEM_RESPONSES,
)
def get_transfer_intent(
    intent_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> TransferIntentResponse:
    intent = transfer_intents_service(request).get(actor=actor, intent_id=EntityId(intent_id))
    return TransferIntentResponse.from_intent(intent)


@router.patch(
    "/transfer-intents/{intent_id}",
    operation_id="revise_transfer_intent",
    response_model=TransferIntentResponse,
    responses=PROBLEM_RESPONSES,
)
def revise_transfer_intent(
    intent_id: UUID,
    payload: ReviseTransferIntentBody,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> TransferIntentResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    intent = transfer_intents_service(request).revise(
        actor=actor,
        intent_id=EntityId(intent_id),
        expected_revision=payload.expected_revision,
        profile_id=EntityId(payload.profile_id),
        amount=Money(payload.amount_minor, Currency.RUB),
        recipient_code=payload.recipient_code,
        idempotency_key=key,
    )
    return TransferIntentResponse.from_intent(intent)


@router.post(
    "/transfer-intents/{intent_id}/checks",
    operation_id="create_transfer_check",
    status_code=status.HTTP_201_CREATED,
    response_model=TransferCheckResponse,
    responses=PROBLEM_RESPONSES,
)
def create_transfer_check(
    intent_id: UUID,
    payload: CreateTransferCheckBody,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> TransferCheckResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    view = transfer_checks_service(request).create(
        actor=actor,
        intent_id=EntityId(intent_id),
        expected_revision=payload.expected_revision,
        linked_incident_id=EntityId(payload.linked_incident_id)
        if payload.linked_incident_id
        else None,
        idempotency_key=key,
    )
    return TransferCheckResponse.from_view(view)


@router.get(
    "/transfer-intents/{intent_id}/checks",
    operation_id="list_transfer_checks",
    response_model=TransferChecksResponse,
    responses=PROBLEM_RESPONSES,
)
def list_transfer_checks(
    intent_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> TransferChecksResponse:
    views = transfer_checks_service(request).list_for_intent(
        actor=actor, intent_id=EntityId(intent_id)
    )
    return TransferChecksResponse(items=[TransferCheckResponse.from_view(view) for view in views])


@router.get(
    "/transfer-checks/{check_id}",
    operation_id="get_transfer_check",
    response_model=TransferCheckResponse,
    responses=PROBLEM_RESPONSES,
)
def get_transfer_check(
    check_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> TransferCheckResponse:
    view = transfer_checks_service(request).get(actor=actor, check_id=EntityId(check_id))
    return TransferCheckResponse.from_view(view)


@router.post(
    "/transfer-intents/{intent_id}/execute",
    operation_id="execute_transfer_intent",
    response_model=TransferCompletionResponse,
    responses=PROBLEM_RESPONSES,
)
def execute_transfer_intent(
    intent_id: UUID,
    payload: ExecuteTransferBody,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> TransferCompletionResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    result = complete_transfer_service(request).execute(
        actor=actor,
        intent_id=EntityId(intent_id),
        check_id=EntityId(payload.check_id),
        expected_revision=payload.expected_revision,
        acknowledge_warning=payload.acknowledge_warning,
        idempotency_key=key,
    )
    return TransferCompletionResponse.from_result(result)


@router.post(
    "/transfer-intents/{intent_id}/cancel",
    operation_id="cancel_transfer_intent",
    response_model=TransferCompletionResponse,
    responses=PROBLEM_RESPONSES,
)
def cancel_transfer_intent(
    intent_id: UUID,
    payload: CancelTransferBody,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> TransferCompletionResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    result = complete_transfer_service(request).cancel(
        actor=actor,
        intent_id=EntityId(intent_id),
        expected_revision=payload.expected_revision,
        idempotency_key=key,
    )
    return TransferCompletionResponse.from_result(result)
