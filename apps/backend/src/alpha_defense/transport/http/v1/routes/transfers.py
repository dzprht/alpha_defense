"""Owner-scoped synthetic finance profiles; transfer UI arrives in P24."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from alpha_defense.application.shared import ActorContext
from alpha_defense.application.transfers import EntityId
from alpha_defense.transport.http.v1.dependencies import (
    current_actor,
    financial_profiles_service,
)
from alpha_defense.transport.http.v1.guards import require_csrf, require_idempotency_key
from alpha_defense.transport.http.v1.schemas.transfers import (
    CreateProfileBody,
    FinancialProfileResponse,
    FinancialProfilesResponse,
    ProfileTemplateResponse,
    ProfileTemplatesResponse,
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
