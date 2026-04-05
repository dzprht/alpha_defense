"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from alpha_protect.infrastructure.settings import get_settings
from alpha_protect.presentation.routers.awareness import router as awareness_router
from alpha_protect.presentation.routers.calls import router as calls_router
from alpha_protect.presentation.routers.intel import router as intel_router
from alpha_protect.presentation.routers.registry import router as registry_router
from alpha_protect.presentation.routers.responses import router as responses_router
from alpha_protect.presentation.routers.signals import router as signals_router
from alpha_protect.presentation.routers.system import router as system_router

TAGS_METADATA = [
    {"name": "system", "description": "Technical system endpoints."},
    {"name": "signals", "description": "Signal ingestion and call verification."},
    {"name": "intel", "description": "External intelligence provider checks."},
    {"name": "registry", "description": "Threat registry operations."},
    {"name": "responses", "description": "Automated mitigation actions."},
    {"name": "awareness", "description": "Financial literacy and user prompts."},
]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        openapi_tags=TAGS_METADATA,
    )

    app.include_router(system_router)
    app.include_router(signals_router, prefix=settings.api_prefix)
    app.include_router(calls_router, prefix=settings.api_prefix)
    app.include_router(intel_router, prefix=settings.api_prefix)
    app.include_router(registry_router, prefix=settings.api_prefix)
    app.include_router(responses_router, prefix=settings.api_prefix)
    app.include_router(awareness_router, prefix=settings.api_prefix)
    return app


app = create_app()
