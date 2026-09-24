"""Owner-scoped contact intake, assessment history, and reassessment endpoints."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from alpha_defense.application.communications import EntityId
from alpha_defense.application.shared import ActorContext
from alpha_defense.transport.http.v1.dependencies import (
    complete_contact_service,
    current_actor,
    get_incident_service,
    get_observation_service,
)
from alpha_defense.transport.http.v1.guards import require_csrf, require_idempotency_key
from alpha_defense.transport.http.v1.schemas.contact import (
    AssessmentResponse,
    ContactAnalysisResponse,
    GuidanceResponse,
    IncidentResponse,
    ObservationResponse,
)
from alpha_defense.transport.http.v1.schemas.observations import ManualObservationInputSchema

router = APIRouter(tags=["contact"])

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {
        "description": "Problem Details",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        },
    }
    for code in (400, 401, 403, 404, 409, 422, 503)
}


@router.post(
    "/observations",
    operation_id="submit_observation",
    status_code=status.HTTP_201_CREATED,
    response_model=ContactAnalysisResponse,
    responses=PROBLEM_RESPONSES,
)
def submit_observation(
    payload: ManualObservationInputSchema,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> ContactAnalysisResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    result = complete_contact_service(request).submit(
        actor=actor, observation_input=payload.to_input(), idempotency_key=key
    )
    return ContactAnalysisResponse.from_result(result)


@router.get(
    "/observations/{observation_id}",
    operation_id="get_observation",
    response_model=ObservationResponse,
    responses=PROBLEM_RESPONSES,
)
def get_observation(
    observation_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> ObservationResponse:
    view = get_observation_service(request).execute(
        actor=actor, observation_id=EntityId(observation_id)
    )
    return ObservationResponse.from_view(view)


@router.get(
    "/incidents/{incident_id}",
    operation_id="get_incident",
    response_model=IncidentResponse,
    responses=PROBLEM_RESPONSES,
)
def get_incident(
    incident_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> IncidentResponse:
    view = get_incident_service(request).execute(actor=actor, incident_id=EntityId(incident_id))
    return IncidentResponse.from_view(view)


@router.get(
    "/assessments/{assessment_id}",
    operation_id="get_assessment",
    response_model=AssessmentResponse,
    responses=PROBLEM_RESPONSES,
)
def get_assessment(
    assessment_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> AssessmentResponse:
    value = complete_contact_service(request).get_assessment(
        actor=actor, assessment_id=EntityId(assessment_id)
    )
    return AssessmentResponse.from_assessment(value)


@router.get(
    "/assessments/{assessment_id}/guidance",
    operation_id="get_assessment_guidance",
    response_model=GuidanceResponse,
    responses=PROBLEM_RESPONSES,
)
def get_assessment_guidance(
    assessment_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
    locale: Annotated[str, Query(pattern=r"^[a-z]{2}-[A-Z]{2}$")] = "ru-RU",
) -> GuidanceResponse:
    view = complete_contact_service(request).get_guidance(
        actor=actor, assessment_id=EntityId(assessment_id), locale=locale
    )
    return GuidanceResponse.from_view(view)


@router.post(
    "/observations/{observation_id}/reassess",
    operation_id="reassess_observation",
    status_code=status.HTTP_201_CREATED,
    response_model=ContactAnalysisResponse,
    responses=PROBLEM_RESPONSES,
)
def reassess_observation(
    observation_id: UUID,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> ContactAnalysisResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    result = complete_contact_service(request).reassess(
        actor=actor,
        observation_id=EntityId(observation_id),
        idempotency_key=key,
    )
    return ContactAnalysisResponse.from_result(result)
