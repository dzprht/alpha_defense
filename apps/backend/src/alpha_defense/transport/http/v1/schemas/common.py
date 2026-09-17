"""Common public response schemas."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=255)


class ProblemDetails(BaseModel):
    """RFC 9457 response extended with stable application fields."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=128)
    status: int = Field(ge=400, le=599)
    detail: str = Field(min_length=1, max_length=512)
    instance: str = Field(min_length=1, max_length=2048)
    code: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=36, max_length=36)
    field_errors: tuple[FieldError, ...] | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def _omit_empty_field_errors(self) -> Self:
        if self.field_errors == ():
            raise ValueError("field_errors must be omitted instead of empty")
        return self
