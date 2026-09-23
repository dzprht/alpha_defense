"""ASGI application factory and production composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import Lifespan

from alpha_defense.application.education import GetCard, ListCards
from alpha_defense.application.identity import AccountServicePort, IdentityServicePort
from alpha_defense.application.ports import ReadinessPort
from alpha_defense.bootstrap.container import build_container
from alpha_defense.bootstrap.settings import AppEnvironment, Settings
from alpha_defense.transport.http.v1 import api_v1_router
from alpha_defense.transport.http.v1.dependencies import CookiePolicy
from alpha_defense.transport.http.v1.errors import install_exception_handlers
from alpha_defense.transport.http.v1.middleware import RequestContextMiddleware


def create_http_app(
    *,
    readiness: ReadinessPort,
    max_request_body_bytes: int = 1_048_576,
    cors_origins: tuple[str, ...] = ("http://localhost:5173",),
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver"),
    identity_service: IdentityServicePort | None = None,
    account_service: AccountServicePort | None = None,
    list_cards: ListCards | None = None,
    get_card: GetCard | None = None,
    secure_cookies: bool = False,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Build HTTP delivery independently from infrastructure for tests and export."""

    app = FastAPI(
        title="Alpha Defense API",
        version="1.0.0",
        description="Synthetic-data anti-fraud prototype API.",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.readiness = readiness
    app.state.identity_service = identity_service
    app.state.account_service = account_service
    app.state.list_cards = list_cards
    app.state.get_card = get_card
    app.state.cookie_policy = CookiePolicy(secure=secure_cookies)
    app.include_router(api_v1_router)
    install_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-CSRF-Token", "X-Request-ID"],
    )
    app.add_middleware(
        RequestContextMiddleware,
        max_body_bytes=max_request_body_bytes,
        allowed_hosts=allowed_hosts,
    )
    return app


def create_app() -> FastAPI:
    """Load environment, fail fast, and return the executable ASGI application."""

    settings = Settings()
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            container.close()

    app = create_http_app(
        readiness=container.readiness,
        max_request_body_bytes=settings.max_request_body_bytes,
        cors_origins=settings.cors_origins,
        allowed_hosts=settings.allowed_hosts,
        identity_service=container.identity_service,
        account_service=container.account_service,
        list_cards=container.list_cards,
        get_card=container.get_card,
        secure_cookies=settings.app_env is AppEnvironment.PRODUCTION,
        lifespan=lifespan,
    )
    app.state.container = container
    return app
