"""Public route registry for API version 1."""

from fastapi import APIRouter

from alpha_defense.transport.http.v1.routes.health import router as health_router
from alpha_defense.transport.http.v1.routes.identity import router as identity_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(identity_router)
