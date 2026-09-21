"""Server-derived session, owner, namespace, and role dependencies."""

# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import Request

from alpha_defense.application.education import GetCard, ListCards
from alpha_defense.application.identity import IdentityServicePort
from alpha_defense.application.shared import (
    ActionForbiddenError,
    ActorContext,
    ActorRole,
    ResourceNotFoundError,
    SessionRequiredError,
)

SESSION_COOKIE_NAME = "alpha_defense_session"
PRE_SESSION_COOKIE_NAME = "alpha_defense_pre_session"
CSRF_COOKIE_NAME = "alpha_defense_csrf"


@dataclass(frozen=True, slots=True)
class CookiePolicy:
    secure: bool
    session_max_age: int = 43_200
    pre_session_max_age: int = 300


def identity_service(request: Request) -> IdentityServicePort:
    service = getattr(request.app.state, "identity_service", None)
    if service is None:
        raise RuntimeError("identity service was not configured")
    return cast(IdentityServicePort, service)


def list_cards_service(request: Request) -> ListCards:
    service = getattr(request.app.state, "list_cards", None)
    if not isinstance(service, ListCards):
        raise RuntimeError("list cards service was not configured")
    return service


def get_card_service(request: Request) -> GetCard:
    service = getattr(request.app.state, "get_card", None)
    if not isinstance(service, GetCard):
        raise RuntimeError("get card service was not configured")
    return service


def current_actor(request: Request) -> ActorContext:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise SessionRequiredError("Требуется действующая демонстрационная сессия.")
    return identity_service(request).resolve_actor(token)


def require_owner(actor: ActorContext, owner_id: str) -> None:
    if str(actor.user_id) != owner_id:
        raise ResourceNotFoundError("Ресурс не найден.")


def require_namespace(actor: ActorContext, namespace_id: str) -> None:
    if str(actor.namespace_id) != namespace_id:
        raise ResourceNotFoundError("Ресурс не найден.")


def require_role(actor: ActorContext, role: ActorRole) -> None:
    if not actor.has_role(role):
        raise ActionForbiddenError("Действие недоступно для текущей роли.")
