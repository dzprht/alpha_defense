"""Owner-scoped warning read and browser presentation acknowledgement."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from alpha_defense.application.communications import EntityId
from alpha_defense.application.shared import ActorContext
from alpha_defense.transport.http.v1.dependencies import (
    complete_contact_service,
    current_actor,
    warning_service,
)
from alpha_defense.transport.http.v1.guards import require_csrf, require_idempotency_key
from alpha_defense.transport.http.v1.schemas.protection import (
    WarningLookupResponse,
    WarningResponse,
)

router = APIRouter(tags=["protection"])

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {
        "description": "Problem Details",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        },
    }
    for code in (400, 401, 403, 404, 409, 503)
}


@router.get(
    "/assessments/{assessment_id}/warning",
    operation_id="get_assessment_warning",
    response_model=WarningLookupResponse,
    responses=PROBLEM_RESPONSES,
)
def get_assessment_warning(
    assessment_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> WarningLookupResponse:
    value = EntityId(assessment_id)
    complete_contact_service(request).get_assessment(actor=actor, assessment_id=value)
    warning = warning_service(request).get_by_assessment(actor=actor, assessment_id=value)
    return WarningLookupResponse(
        warning=None if warning is None else WarningResponse.from_warning(warning)
    )


@router.post(
    "/warnings/{warning_id}/present",
    operation_id="present_warning",
    response_model=WarningResponse,
    responses=PROBLEM_RESPONSES,
)
def present_warning(
    warning_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> WarningResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    warning = warning_service(request).present(
        actor=actor, warning_id=EntityId(warning_id), idempotency_key=key
    )
    return WarningResponse.from_warning(warning)
