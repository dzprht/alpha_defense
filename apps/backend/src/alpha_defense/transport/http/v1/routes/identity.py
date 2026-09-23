"""Synthetic session bootstrap and explicit consent endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from alpha_defense.application.identity import (
    AnonymousSessionView,
    ConsentScope,
    SessionView,
    StartSessionResult,
)
from alpha_defense.application.shared import ActorContext, SessionRequiredError
from alpha_defense.transport.http.v1.dependencies import (
    CSRF_COOKIE_NAME,
    PRE_SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    CookiePolicy,
    account_service,
    current_actor,
    identity_service,
)
from alpha_defense.transport.http.v1.guards import require_csrf, require_idempotency_key
from alpha_defense.transport.http.v1.schemas import (
    AccountCredentialsRequest,
    AnonymousSessionResponse,
    ConsentResponse,
    SessionResponse,
    StartDemoSessionRequest,
    UpdateConsentRequest,
)

router = APIRouter(tags=["identity"])

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {
        "description": "Problem Details",
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        },
    }
    for code in (400, 401, 403, 409, 422, 429, 503)
}


@router.get(
    "/session",
    operation_id="get_session",
    response_model=AnonymousSessionResponse | SessionResponse,
    responses={503: PROBLEM_RESPONSES[503]},
)
def get_session(request: Request, response: Response) -> AnonymousSessionResponse | SessionResponse:
    result = identity_service(request).bootstrap_session(
        session_token=request.cookies.get(SESSION_COOKIE_NAME),
        pre_session_token=request.cookies.get(PRE_SESSION_COOKIE_NAME),
    )
    policy = _cookie_policy(request)
    _set_csrf_cookie(response, result.csrf_token, policy)
    if result.session_token is not None:
        if not isinstance(result.view, SessionView):
            raise RuntimeError("active bootstrap returned an anonymous view")
        _set_private_cookie(
            response,
            SESSION_COOKIE_NAME,
            result.session_token,
            max_age=policy.session_max_age,
            policy=policy,
        )
        response.delete_cookie(PRE_SESSION_COOKIE_NAME, path="/", samesite="lax")
        return SessionResponse.from_view(result.view)
    if result.pre_session_token is None:
        raise RuntimeError("anonymous bootstrap did not return a pre-session token")
    _set_private_cookie(
        response,
        PRE_SESSION_COOKIE_NAME,
        result.pre_session_token,
        max_age=policy.pre_session_max_age,
        policy=policy,
    )
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="lax")
    if not isinstance(result.view, AnonymousSessionView):
        raise RuntimeError("anonymous bootstrap returned an active view")
    return AnonymousSessionResponse.from_view(result.view)


@router.post(
    "/sessions/demo",
    operation_id="start_demo_session",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionResponse,
    responses=PROBLEM_RESPONSES,
)
def start_demo_session(
    payload: StartDemoSessionRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    require_csrf(request)
    idempotency_key = require_idempotency_key(request)
    pre_session_token = request.cookies.get(PRE_SESSION_COOKIE_NAME)
    if not pre_session_token:
        raise SessionRequiredError("Сначала получите pre-session через GET /session.")
    result = identity_service(request).start_session(
        pre_session_token=pre_session_token,
        idempotency_key=idempotency_key,
        profile_code=payload.profile_code,
    )
    policy = _cookie_policy(request)
    _set_private_cookie(
        response,
        SESSION_COOKIE_NAME,
        result.session_token,
        max_age=policy.session_max_age,
        policy=policy,
    )
    _set_csrf_cookie(response, result.csrf_token, policy)
    response.delete_cookie(PRE_SESSION_COOKIE_NAME, path="/", samesite="lax")
    return SessionResponse.from_view(result.view)


@router.post(
    "/accounts",
    operation_id="register_account",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionResponse,
    responses=PROBLEM_RESPONSES,
)
def register_account(
    payload: AccountCredentialsRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    pre_token = request.cookies.get(PRE_SESSION_COOKIE_NAME)
    if not pre_token:
        raise SessionRequiredError("Сначала получите pre-session через GET /session.")
    result = account_service(request).register(
        pre_session_token=pre_token,
        idempotency_key=key,
        login=payload.login,
        password=payload.password,
    )
    return _deliver_account_session(request, response, result)


@router.post(
    "/sessions",
    operation_id="login_account",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionResponse,
    responses=PROBLEM_RESPONSES,
)
def login_account(
    payload: AccountCredentialsRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    require_csrf(request)
    key = require_idempotency_key(request)
    pre_token = request.cookies.get(PRE_SESSION_COOKIE_NAME)
    if not pre_token:
        raise SessionRequiredError("Сначала получите pre-session через GET /session.")
    result = account_service(request).login(
        pre_session_token=pre_token,
        idempotency_key=key,
        login=payload.login,
        password=payload.password,
    )
    return _deliver_account_session(request, response, result)


@router.post(
    "/sessions/logout",
    operation_id="logout_session",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=PROBLEM_RESPONSES,
)
def logout_session(request: Request, response: Response) -> None:
    require_csrf(request)
    key = require_idempotency_key(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise SessionRequiredError("Требуется действующая сессия.")
    account_service(request).logout(session_token=token, idempotency_key=key)
    for cookie in (SESSION_COOKIE_NAME, PRE_SESSION_COOKIE_NAME, CSRF_COOKIE_NAME):
        response.delete_cookie(cookie, path="/", samesite="lax")


def _deliver_account_session(
    request: Request, response: Response, result: StartSessionResult
) -> SessionResponse:
    policy = _cookie_policy(request)
    _set_private_cookie(
        response,
        SESSION_COOKIE_NAME,
        result.session_token,
        max_age=policy.session_max_age,
        policy=policy,
    )
    _set_csrf_cookie(response, result.csrf_token, policy)
    response.delete_cookie(PRE_SESSION_COOKIE_NAME, path="/", samesite="lax")
    return SessionResponse.from_view(result.view)


@router.patch(
    "/consents/{scope}",
    operation_id="update_consent",
    response_model=ConsentResponse,
    responses=PROBLEM_RESPONSES,
)
def update_consent(
    scope: ConsentScope,
    payload: UpdateConsentRequest,
    request: Request,
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> ConsentResponse:
    require_csrf(request)
    idempotency_key = require_idempotency_key(request)
    view = identity_service(request).update_consent(
        actor=actor,
        idempotency_key=idempotency_key,
        scope=scope,
        status=payload.status,
        expected_revision=payload.expected_revision,
    )
    return ConsentResponse.from_view(view)


def _cookie_policy(request: Request) -> CookiePolicy:
    policy = getattr(request.app.state, "cookie_policy", None)
    if not isinstance(policy, CookiePolicy):
        raise RuntimeError("cookie policy was not configured")
    return policy


def _set_private_cookie(
    response: Response,
    name: str,
    value: str,
    *,
    max_age: int,
    policy: CookiePolicy,
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=policy.secure,
        samesite="lax",
        path="/",
    )


def _set_csrf_cookie(response: Response, value: str, policy: CookiePolicy) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        value,
        max_age=policy.session_max_age,
        httponly=False,
        secure=policy.secure,
        samesite="lax",
        path="/",
    )
