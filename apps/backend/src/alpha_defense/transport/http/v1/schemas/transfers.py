"""Public synthetic profile and immutable history representation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from alpha_defense.application.transfers import (
    FinancialProfile,
    ProfileTemplate,
    TransferCheckView,
    TransferCompletion,
    TransferIntent,
)


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


class CreateTransferIntentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: UUID
    amount_minor: int = Field(strict=True, ge=1, le=100_000_000)
    recipient_code: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")


class ReviseTransferIntentBody(CreateTransferIntentBody):
    expected_revision: int = Field(strict=True, ge=1)


class TransferIntentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    profile_id: str
    amount_minor: int
    currency: str
    recipient_code: str
    revision: int
    fingerprint: str
    status: str
    created_at: datetime
    updated_at: datetime
    execution_mode: str

    @classmethod
    def from_intent(cls, intent: TransferIntent) -> TransferIntentResponse:
        return cls(
            intent_id=str(intent.intent_id),
            profile_id=str(intent.profile_id),
            amount_minor=intent.amount.amount_minor,
            currency=intent.amount.currency.value,
            recipient_code=intent.recipient_code,
            revision=intent.revision,
            fingerprint=intent.fingerprint,
            status=intent.status.value,
            created_at=intent.created_at,
            updated_at=intent.updated_at,
            execution_mode="mock",
        )


class TransferIntentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TransferIntentResponse]


class ExecuteTransferBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: UUID
    expected_revision: int = Field(strict=True, ge=1)
    acknowledge_warning: bool = Field(strict=True)


class CancelTransferBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(strict=True, ge=1)


class TransferCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: TransferIntentResponse
    operation_id: str | None
    completed_at: datetime | None
    execution_mode: str

    @classmethod
    def from_result(cls, result: TransferCompletion) -> TransferCompletionResponse:
        return cls(
            intent=TransferIntentResponse.from_intent(result.intent),
            operation_id=str(result.bank_result.operation_id) if result.bank_result else None,
            completed_at=result.bank_result.recorded_at if result.bank_result else None,
            execution_mode="mock",
        )


class CreateTransferCheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(strict=True, ge=1)
    linked_incident_id: UUID | None = None


class TransferCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    intent_id: str
    intent_revision: int
    intent_fingerprint: str
    profile_id: str
    history_version: int
    consent_revision: int
    ingress_epoch: int
    linked_incident_id: str | None
    context_version: int | None
    contact_assessment_id: str | None
    model_version: str | None
    policy_version: str
    catalog_policy_version: str
    registry_snapshot_id: str | None
    registry_version: str | None
    registry_valid_until: datetime | None
    behavior_status: str
    sample_size: int
    recipient_is_new: bool | None
    amount_is_outlier: bool | None
    recipient_lookup: str
    contact_status: str
    severity: str
    score: int | None
    completeness: str
    decision: str
    signal_codes: list[str]
    reason_codes: list[str]
    checked_at: datetime
    expires_at: datetime
    fresh: bool
    stale_reasons: list[str]
    execution_mode: str

    @classmethod
    def from_view(cls, view: TransferCheckView) -> TransferCheckResponse:
        check = view.check
        return cls(
            check_id=str(check.check_id),
            intent_id=str(check.intent_id),
            intent_revision=check.intent_revision,
            intent_fingerprint=check.intent_fingerprint,
            profile_id=str(check.profile_id),
            history_version=check.history_version,
            consent_revision=check.consent_revision,
            ingress_epoch=check.ingress_epoch,
            linked_incident_id=str(check.linked_incident_id) if check.linked_incident_id else None,
            context_version=check.context_version,
            contact_assessment_id=str(check.contact_assessment_id)
            if check.contact_assessment_id
            else None,
            model_version=check.model_version,
            policy_version=check.policy_version,
            catalog_policy_version=check.catalog_policy_version,
            registry_snapshot_id=str(check.registry_snapshot_id)
            if check.registry_snapshot_id
            else None,
            registry_version=check.registry_version,
            registry_valid_until=check.registry_valid_until,
            behavior_status=check.behavior_status.value,
            sample_size=check.sample_size,
            recipient_is_new=check.recipient_is_new,
            amount_is_outlier=check.amount_is_outlier,
            recipient_lookup=check.recipient_lookup.value,
            contact_status=check.contact_status.value,
            severity=check.severity.value,
            score=check.score,
            completeness=check.completeness.value,
            decision=check.decision.value,
            signal_codes=list(check.signal_codes),
            reason_codes=list(check.reason_codes),
            checked_at=check.checked_at,
            expires_at=check.expires_at,
            fresh=view.fresh,
            stale_reasons=list(view.stale_reasons),
            execution_mode="mock",
        )


class TransferChecksResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TransferCheckResponse]
