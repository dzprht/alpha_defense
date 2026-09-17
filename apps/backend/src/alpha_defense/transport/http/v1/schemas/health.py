"""Health endpoint response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DependencyStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    status: Literal["ready"] = "ready"


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["alive"] = "alive"
    request_id: str = Field(min_length=36, max_length=36)


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"] = "ready"
    request_id: str = Field(min_length=36, max_length=36)
    checks: tuple[DependencyStatus, ...] = Field(min_length=1)
