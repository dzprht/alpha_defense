"""Published education catalog endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request

from alpha_defense.application.shared import ActorContext, PageRequest
from alpha_defense.transport.http.v1.dependencies import (
    current_actor,
    get_card_service,
    list_cards_service,
)
from alpha_defense.transport.http.v1.schemas import (
    EducationCardPageResponse,
    EducationCardResponse,
)

router = APIRouter(prefix="/education", tags=["education"])

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {
        "description": "Problem Details",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        },
    }
    for code in (401, 422, 503)
}


@router.get(
    "/cards",
    operation_id="list_education_cards",
    response_model=EducationCardPageResponse,
    responses=PROBLEM_RESPONSES,
)
def list_education_cards(
    request: Request,
    _actor: Annotated[ActorContext, Depends(current_actor)],
    locale: Annotated[str, Query(pattern=r"^[a-z]{2}-[A-Z]{2}$")] = "ru-RU",
    cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> EducationCardPageResponse:
    view = list_cards_service(request).execute(
        page=PageRequest(cursor=cursor, limit=limit),
        locale=locale,
    )
    return EducationCardPageResponse.from_view(view)


@router.get(
    "/cards/{code}",
    operation_id="get_education_card",
    response_model=EducationCardResponse,
    responses=PROBLEM_RESPONSES,
)
def get_education_card(
    request: Request,
    _actor: Annotated[ActorContext, Depends(current_actor)],
    code: Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{1,63}$")],
    locale: Annotated[str, Query(pattern=r"^[a-z]{2}-[A-Z]{2}$")] = "ru-RU",
    version: Annotated[
        str | None,
        Query(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"),
    ] = None,
) -> EducationCardResponse:
    return EducationCardResponse.from_view(
        get_card_service(request).execute(code=code, locale=locale, version=version)
    )
