"""Public route registry for API version 1."""

from fastapi import APIRouter

from alpha_defense.transport.http.v1.routes.contact import router as contact_router
from alpha_defense.transport.http.v1.routes.education import router as education_router
from alpha_defense.transport.http.v1.routes.health import router as health_router
from alpha_defense.transport.http.v1.routes.identity import router as identity_router
from alpha_defense.transport.http.v1.routes.protection import router as protection_router
from alpha_defense.transport.http.v1.routes.transfers import router as transfers_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(identity_router)
api_v1_router.include_router(education_router)
api_v1_router.include_router(contact_router)
api_v1_router.include_router(protection_router)
api_v1_router.include_router(transfers_router)
