"""Public synthetic profile and immutable history representation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from alpha_defense.application.transfers import FinancialProfile, ProfileTemplate


class CreateProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_code: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")


class ProfileTemplateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    version: str
    title: str
    description: str
    operation_count: int

    @classmethod
    def from_template(cls, template: ProfileTemplate) -> ProfileTemplateResponse:
        return cls(
            code=template.code,
            version=template.version,
            title=template.title,
            description=template.description,
            operation_count=len(template.operations),
        )


class ProfileTemplatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProfileTemplateResponse]


class CompletedOperationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    amount_minor: int
    currency: str
    recipient_code: str
    completed_at: datetime


class FinancialProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    template_code: str
    template_version: str
    title: str
    description: str
    history_version: int
    created_at: datetime
    execution_mode: str
    operations: list[CompletedOperationResponse]

    @classmethod
    def from_profile(cls, profile: FinancialProfile) -> FinancialProfileResponse:
        return cls(
            profile_id=str(profile.profile_id),
            template_code=profile.template_code,
            template_version=profile.template_version,
            title=profile.title,
            description=profile.description,
            history_version=profile.history_version,
            created_at=profile.created_at,
            execution_mode="mock",
            operations=[
                CompletedOperationResponse(
                    operation_id=str(item.operation_id),
                    amount_minor=item.amount.amount_minor,
                    currency=item.amount.currency.value,
                    recipient_code=item.recipient_code,
                    completed_at=item.completed_at,
                )
                for item in profile.operations
            ],
        )


class FinancialProfilesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FinancialProfileResponse]
