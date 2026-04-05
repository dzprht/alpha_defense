"""HTTP response schemas shared across routers."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class NotImplementedStubResponse(BaseModel):
    request_id: UUID
    status: Literal["not_implemented"] = "not_implemented"
    detail: str
    timestamp: datetime
