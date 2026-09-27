"""Owner-scoped, idempotent transfer checks over a single consistent evidence view."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from alpha_defense.application.ports import (
    AuditRecord,
    CatalogLoaderPort,
    Clock,
    EventEnvelope,
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    IdGenerator,
)
from alpha_defense.application.ports.transfer_intents import (
    TransferUnitOfWorkFactory,
    TransferUnitOfWorkPort,
)
from alpha_defense.application.shared import (
    ActionInProgressError,
    ActorContext,
    ConsentRequiredError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    StaleRevisionError,
    ValidationError,
)
from alpha_defense.domain.detection import (
    AnalyzerKind,
    AssessmentCompleteness,
    AssessmentTargetKind,
)
from alpha_defense.domain.identity import ConsentScope, ConsentStatus
from alpha_defense.domain.incidents import Incident
from alpha_defense.domain.shared import EntityId
from alpha_defense.domain.threats import IndicatorType, ThreatIndicator
from alpha_defense.domain.transfers import (
    CHECK_TTL,
    TRANSFER_POLICY_VERSION,
    ContactEvidenceStatus,
    IntentStatus,
    RecipientLookupStatus,
    TransferCheck,
    TransferCheckPolicy,
    TransferIntent,
    assess_history,
)


@dataclass(frozen=True, slots=True)
class TransferCheckView:
    check: TransferCheck
    stale_reasons: tuple[str, ...]

    @property
    def fresh(self) -> bool:
        return not self.stale_reasons


class TransferChecks:
    def __init__(
        self,
        *,
        unit_of_work: TransferUnitOfWorkFactory,
        catalog: CatalogLoaderPort,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._catalog = catalog
        self._clock = clock
        self._ids = id_generator

    def create(
        self,
        *,
        actor: ActorContext,
        intent_id: EntityId,
        expected_revision: int,
        linked_incident_id: EntityId | None,
        idempotency_key: str,
    ) -> TransferCheckView:
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValidationError("Некорректная версия перевода.")
        now = self._clock.now_utc()
        policy = self._catalog.load().policy
        policy_identity = f"{policy.policy_version}:{policy.content_sha256}"
        scorer = TransferCheckPolicy(
            weights={item.code: item.base_score for item in policy.signals},
            low_max=policy.thresholds.low_max,
            medium_max=policy.thresholds.medium_max,
            high_max=policy.thresholds.high_max,
            linked_contact_bonus=policy.linked_contact,
        )
        command = {
            "intent_id": str(intent_id),
            "expected_revision": expected_revision,
            "linked_incident_id": str(linked_incident_id) if linked_incident_id else None,
        }
        candidate = IdempotencyRecord(
            record_id=self._ids.new_id(),
            scope=IdempotencyScope(
                principal_fingerprint=sha256(str(actor.user_id).encode()).hexdigest(),
                session_id=actor.session_id,
                namespace_id=actor.namespace_id,
                method="POST",
                canonical_route="/api/v1/transfer-intents/{intent_id}/checks",
                key=idempotency_key,
            ),
            command_hash=sha256(json.dumps(command, sort_keys=True).encode()).hexdigest(),
            resource_id=self._ids.new_id(),
            state=IdempotencyState.IN_PROGRESS,
            result=None,
            revision=0,
            created_at=now,
            updated_at=now,
        )
        with self._unit_of_work() as uow:
            intent = _owned_intent(uow, actor, intent_id)
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                if reservation.record.state is not IdempotencyState.COMPLETED:
                    raise ActionInProgressError("Проверка перевода ещё выполняется.")
                stored = uow.transfer_checks.get(reservation.record.resource_id)
                if stored is None or stored.owner_id != actor.user_id:
                    raise ServiceUnavailableError("Сохранённая проверка недоступна.")
                return self._view(uow, stored, intent, now, policy_identity)
            if intent.revision != expected_revision:
                raise StaleRevisionError("Версия перевода устарела.")
            if intent.status not in (IntentStatus.DRAFT, IntentStatus.CHECKED):
                raise ValidationError("Этот перевод больше нельзя проверить.")
            profile = uow.profiles.get(intent.profile_id)
            if (
                profile is None
                or profile.owner_id != actor.user_id
                or profile.namespace_id != actor.namespace_id
            ):
                raise ResourceNotFoundError("Профиль не найден.")
            consent = uow.identity.get_consent(actor.user_id, ConsentScope.USE_TRANSACTION_HISTORY)
            if consent is None or consent.status is not ConsentStatus.GRANTED:
                raise ConsentRequiredError("Разрешите использование истории операций.")
            behavior = assess_history(
                profile, amount=intent.amount, recipient_code=intent.recipient_code, as_of=now
            )
            risk_state = uow.namespace_risk_states.get(actor.namespace_id)
            if risk_state is not None and risk_state.owner_id != actor.user_id:
                raise ServiceUnavailableError("Состояние пространства недоступно.")
            epoch = risk_state.ingress_risk_epoch if risk_state else 0
            pending = risk_state.analysis_pending if risk_state else False
            incident = (
                _owned_incident(uow, actor, linked_incident_id) if linked_incident_id else None
            )
            assessment_id = incident.latest_assessment_id if incident else None
            assessment = uow.assessments.get(assessment_id) if assessment_id else None
            contact_status = ContactEvidenceStatus.NOT_SELECTED
            contact_severity = None
            contact_score = None
            model_version = None
            if incident is not None:
                contact_status = ContactEvidenceStatus.UNAVAILABLE
                if (
                    assessment is not None
                    and assessment.owner_id == actor.user_id
                    and assessment.namespace_id == actor.namespace_id
                    and assessment.context_version == incident.context_version
                    and assessment.target_kind is AssessmentTargetKind.OBSERVATION
                    and assessment.target_id in incident.observation_ids
                    and assessment.policy_version == policy.policy_version
                    and not pending
                ):
                    if assessment.completeness is AssessmentCompleteness.COMPLETE:
                        contact_status = ContactEvidenceStatus.COMPLETE
                    elif assessment.completeness is AssessmentCompleteness.PARTIAL:
                        contact_status = ContactEvidenceStatus.PARTIAL
                    contact_severity = assessment.severity
                    contact_score = assessment.score
                    model_version = next(
                        (
                            item.provenance.provider_version
                            for item in assessment.analyzer_results
                            if item.analyzer is AnalyzerKind.TEXT_MODEL
                        ),
                        None,
                    )
            snapshot = uow.threat_registry.get_current()
            recipient_lookup = RecipientLookupStatus.UNAVAILABLE
            registry_valid_until = None
            if snapshot is not None and snapshot.is_available_at(now):
                indicator = ThreatIndicator.from_raw(
                    IndicatorType.ACCOUNT_TOKEN, f"demo-recipient:{intent.recipient_code}"
                )
                matches = snapshot.active_matches(indicator, now=now)
                recipient_lookup = (
                    RecipientLookupStatus.MATCH if matches else RecipientLookupStatus.NO_MATCH
                )
                registry_valid_until = min(
                    (snapshot.valid_until, *(item.expires_at for item in matches))
                )
            outcome = scorer.evaluate(
                behavior=behavior,
                recipient_lookup=recipient_lookup,
                contact_status=contact_status,
                contact_severity=contact_severity,
                contact_score=contact_score,
                analysis_pending=pending,
            )
            expires_at = (
                min(now + CHECK_TTL, registry_valid_until)
                if registry_valid_until
                else now + CHECK_TTL
            )
            check = TransferCheck(
                check_id=candidate.resource_id,
                intent_id=intent.intent_id,
                owner_id=actor.user_id,
                namespace_id=actor.namespace_id,
                intent_revision=intent.revision,
                intent_fingerprint=intent.fingerprint,
                profile_id=profile.profile_id,
                history_version=profile.history_version,
                consent_revision=consent.revision,
                ingress_epoch=epoch,
                linked_incident_id=linked_incident_id,
                context_version=incident.context_version if incident else None,
                contact_assessment_id=assessment_id,
                model_version=model_version,
                policy_version=TRANSFER_POLICY_VERSION,
                catalog_policy_version=policy_identity,
                registry_snapshot_id=snapshot.snapshot_id if snapshot else None,
                registry_version=snapshot.version if snapshot else None,
                registry_valid_until=registry_valid_until,
                behavior_status=behavior.status,
                sample_size=behavior.sample_size,
                recipient_is_new=behavior.recipient_is_new,
                amount_is_outlier=behavior.amount_is_outlier,
                recipient_lookup=recipient_lookup,
                contact_status=contact_status,
                severity=outcome.severity,
                score=outcome.score,
                completeness=outcome.completeness,
                decision=outcome.decision,
                signal_codes=outcome.signal_codes,
                reason_codes=outcome.reason_codes,
                checked_at=now,
                expires_at=expires_at,
            )
            uow.transfer_intents.mark_checked(
                intent.mark_checked(now=now), expected_revision=intent.revision
            )
            uow.transfer_checks.add(check)
            uow.audit.append(
                AuditRecord(
                    event=EventEnvelope(
                        event_id=self._ids.new_id(),
                        event_type="transfer.check.created",
                        aggregate_id=intent.intent_id,
                        aggregate_revision=intent.revision,
                        occurred_at=now,
                        correlation_id=check.check_id,
                        execution_mode=actor.execution_mode,
                        payload={
                            "check_id": str(check.check_id),
                            "decision": check.decision.value,
                            "completeness": check.completeness.value,
                        },
                    ),
                    recorded_at=now,
                    actor_id=actor.user_id,
                    session_id=actor.session_id,
                    namespace_id=actor.namespace_id,
                )
            )
            uow.idempotency.save(
                candidate.finish(
                    state=IdempotencyState.COMPLETED,
                    result={"check_id": str(check.check_id)},
                    updated_at=now,
                ),
                expected_revision=0,
            )
            uow.commit()
            return TransferCheckView(check, ())

    def get(self, *, actor: ActorContext, check_id: EntityId) -> TransferCheckView:
        now = self._clock.now_utc()
        policy = self._catalog.load().policy
        policy_identity = f"{policy.policy_version}:{policy.content_sha256}"
        with self._unit_of_work() as uow:
            check = uow.transfer_checks.get(check_id)
            if (
                check is None
                or check.owner_id != actor.user_id
                or check.namespace_id != actor.namespace_id
            ):
                raise ResourceNotFoundError("Проверка не найдена.")
            intent = _owned_intent(uow, actor, check.intent_id)
            return self._view(uow, check, intent, now, policy_identity)

    def list_for_intent(
        self, *, actor: ActorContext, intent_id: EntityId
    ) -> tuple[TransferCheckView, ...]:
        now = self._clock.now_utc()
        policy = self._catalog.load().policy
        policy_identity = f"{policy.policy_version}:{policy.content_sha256}"
        with self._unit_of_work() as uow:
            intent = _owned_intent(uow, actor, intent_id)
            return tuple(
                self._view(uow, item, intent, now, policy_identity)
                for item in uow.transfer_checks.list_for_intent(intent_id)
            )

    def _view(
        self,
        uow: TransferUnitOfWorkPort,
        check: TransferCheck,
        intent: TransferIntent,
        now: datetime,
        policy_identity: str,
    ) -> TransferCheckView:
        return current_check_view(uow, check, intent, now, policy_identity)


def current_check_view(
    uow: TransferUnitOfWorkPort,
    check: TransferCheck,
    intent: TransferIntent,
    now: datetime,
    policy_identity: str,
) -> TransferCheckView:
    """Use the same freshness rules for display and the atomic execution guard."""

    profile = uow.profiles.get(check.profile_id)
    consent = uow.identity.get_consent(check.owner_id, ConsentScope.USE_TRANSACTION_HISTORY)
    risk_state = uow.namespace_risk_states.get(check.namespace_id)
    incident = uow.incidents.get(check.linked_incident_id) if check.linked_incident_id else None
    snapshot = uow.threat_registry.get_current()
    latest = uow.transfer_checks.get_latest_for_intent(check.intent_id)
    reasons = check.stale_reasons(
        now=now,
        intent=intent,
        history_version=profile.history_version if profile else -1,
        consent_revision=consent.revision
        if consent and consent.status is ConsentStatus.GRANTED
        else -1,
        ingress_epoch=risk_state.ingress_risk_epoch if risk_state else 0,
        analysis_pending=risk_state.analysis_pending if risk_state else False,
        context_version=incident.context_version if incident else None,
        contact_assessment_id=incident.latest_assessment_id if incident else None,
        registry_snapshot_id=snapshot.snapshot_id if snapshot else None,
        catalog_policy_version=policy_identity,
        latest_check_id=latest.check_id if latest else None,
    )
    return TransferCheckView(check, reasons)


def _owned_intent(
    uow: TransferUnitOfWorkPort, actor: ActorContext, intent_id: EntityId
) -> TransferIntent:
    intent = uow.transfer_intents.get(intent_id)
    if (
        intent is None
        or intent.owner_id != actor.user_id
        or intent.namespace_id != actor.namespace_id
    ):
        raise ResourceNotFoundError("Перевод не найден.")
    return intent


def _owned_incident(
    uow: TransferUnitOfWorkPort, actor: ActorContext, incident_id: EntityId
) -> Incident:
    incident = uow.incidents.get(incident_id)
    if (
        incident is None
        or incident.owner_id != actor.user_id
        or incident.namespace_id != actor.namespace_id
    ):
        raise ResourceNotFoundError("Связанный инцидент не найден.")
    return incident
