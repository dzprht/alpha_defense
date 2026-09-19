"""Synthetic session lifecycle and revisioned consent use cases."""

from __future__ import annotations

from datetime import datetime, timedelta

from alpha_defense.application.identity.dto import (
    AnonymousSessionView,
    ConsentView,
    SessionBootstrapResult,
    SessionView,
    StartSessionResult,
)
from alpha_defense.application.identity.ports import (
    DemoIdentityProviderPort,
    IdentityRepositoryPort,
    IdentityServicePort,
    IdentityUnitOfWorkFactory,
    SecurityTokenPort,
)
from alpha_defense.application.ports import (
    AuditRecord,
    Clock,
    EventEnvelope,
    IdempotencyRecord,
    IdempotencyScope,
    IdempotencyState,
    IdGenerator,
)
from alpha_defense.application.shared import (
    ActionInProgressError,
    ActorContext,
    ActorRole,
    FieldViolation,
    ServiceUnavailableError,
    SessionRequiredError,
    StaleRevisionError,
    ValidationError,
)
from alpha_defense.domain.identity import (
    ConsentScope,
    ConsentSnapshot,
    ConsentStatus,
    DemoSession,
    PreSession,
    SyntheticUser,
)
from alpha_defense.domain.shared import EntityId, ExecutionMode

PRE_SESSION_TTL = timedelta(minutes=5)
SESSION_TTL = timedelta(hours=12)


class IdentityService(IdentityServicePort):
    def __init__(
        self,
        unit_of_work: IdentityUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
        provider: DemoIdentityProviderPort,
        tokens: SecurityTokenPort,
        execution_mode: ExecutionMode,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_generator = id_generator
        self._provider = provider
        self._tokens = tokens
        self._execution_mode = execution_mode

    def bootstrap_session(
        self,
        *,
        session_token: str | None,
        pre_session_token: str | None,
    ) -> SessionBootstrapResult:
        now = self._clock.now_utc()
        if session_token:
            with self._unit_of_work() as uow:
                session = uow.identity.get_session_by_fingerprint(
                    self._tokens.fingerprint(session_token)
                )
                if session is not None and session.is_active_at(now):
                    view = self._session_view(uow.identity, session)
                    return SessionBootstrapResult(
                        view=view,
                        session_token=session_token,
                        csrf_token=self._tokens.derive_csrf_token(session_token),
                    )

        if pre_session_token:
            with self._unit_of_work() as uow:
                pre_session = uow.identity.get_pre_session_by_fingerprint(
                    self._tokens.fingerprint(pre_session_token)
                )
                if pre_session is not None and pre_session.is_available_at(now):
                    return SessionBootstrapResult(
                        view=AnonymousSessionView(
                            pre_session_expires_at=pre_session.expires_at,
                            execution_mode=self._execution_mode,
                        ),
                        pre_session_token=pre_session_token,
                        csrf_token=self._tokens.derive_csrf_token(pre_session_token),
                    )

        token = self._tokens.new_pre_session_token()
        pre_session = PreSession(
            pre_session_id=self._id_generator.new_id(),
            token_fingerprint=self._tokens.fingerprint(token),
            created_at=now,
            expires_at=now + PRE_SESSION_TTL,
        )
        with self._unit_of_work() as uow:
            uow.identity.add_pre_session(pre_session)
            uow.commit()
        return SessionBootstrapResult(
            view=AnonymousSessionView(
                pre_session_expires_at=pre_session.expires_at,
                execution_mode=self._execution_mode,
            ),
            pre_session_token=token,
            csrf_token=self._tokens.derive_csrf_token(token),
        )

    def start_session(
        self,
        *,
        pre_session_token: str,
        idempotency_key: str,
        profile_code: str,
    ) -> StartSessionResult:
        now = self._clock.now_utc()
        pre_fingerprint = self._tokens.fingerprint(pre_session_token)
        scope = IdempotencyScope(
            principal_fingerprint=pre_fingerprint,
            method="POST",
            canonical_route="/api/v1/sessions/demo",
            key=idempotency_key,
        )
        candidate = IdempotencyRecord(
            record_id=self._id_generator.new_id(),
            scope=scope,
            command_hash=self._tokens.fingerprint_command({"profile_code": profile_code}),
            resource_id=self._id_generator.new_id(),
            state=IdempotencyState.IN_PROGRESS,
            result=None,
            revision=0,
            created_at=now,
            updated_at=now,
        )
        with self._unit_of_work() as uow:
            reservation = uow.idempotency.reserve(candidate)
            pre_session = uow.identity.get_pre_session_by_fingerprint(pre_fingerprint)
            if not reservation.is_new:
                return self._replay_start(
                    uow.identity,
                    reservation.record,
                    pre_session=pre_session,
                    pre_session_token=pre_session_token,
                    now=now,
                )
            if pre_session is None or not pre_session.is_available_at(now):
                raise SessionRequiredError("Сначала обновите состояние демонстрационной сессии.")
            subject = self._provider.authenticate(profile_code)
            if subject is None:
                raise ValidationError(
                    "Выберите известный синтетический профиль.",
                    field_errors=(
                        FieldViolation(
                            field="profile_code",
                            code="unknown_profile",
                            message="Неизвестный синтетический профиль.",
                        ),
                    ),
                )

            session_id = reservation.record.resource_id
            session_token = self._tokens.derive_session_token(pre_session_token, session_id)
            user = SyntheticUser(
                user_id=self._id_generator.new_id(),
                profile_code=subject.profile_code,
                created_at=now,
            )
            session = DemoSession(
                session_id=session_id,
                user_id=user.user_id,
                manual_namespace_id=self._id_generator.new_id(),
                roles=subject.roles,
                token_fingerprint=self._tokens.fingerprint(session_token),
                consent_revision=0,
                created_at=now,
                expires_at=now + SESSION_TTL,
            )
            consents = tuple(
                ConsentSnapshot(
                    user_id=user.user_id,
                    scope=consent_scope,
                    status=ConsentStatus.REVOKED,
                    revision=0,
                    changed_at=now,
                )
                for consent_scope in ConsentScope
            )
            uow.identity.add_user(user)
            uow.identity.add_session(session)
            for consent in consents:
                uow.identity.add_consent(consent)
            uow.identity.save_pre_session(
                pre_session.consume(session_id, now=now),
                expected_consumed_session_id=None,
            )
            uow.audit.append(
                self._audit_record(
                    event_type="session.started",
                    aggregate_id=session_id,
                    aggregate_revision=0,
                    correlation_id=session_id,
                    payload={"execution_mode": self._execution_mode.value},
                    actor_id=user.user_id,
                    session_id=session_id,
                    namespace_id=session.manual_namespace_id,
                    now=now,
                )
            )
            completed = reservation.record.finish(
                state=IdempotencyState.COMPLETED,
                result={"session_id": str(session_id)},
                updated_at=now,
            )
            uow.idempotency.save(completed, expected_revision=0)
            uow.commit()

        return StartSessionResult(
            view=SessionView.from_session(
                session,
                consents,
                execution_mode=self._execution_mode,
            ),
            session_token=session_token,
            csrf_token=self._tokens.derive_csrf_token(session_token),
            replayed=False,
        )

    def resolve_actor(self, session_token: str) -> ActorContext:
        now = self._clock.now_utc()
        with self._unit_of_work() as uow:
            session = uow.identity.get_session_by_fingerprint(
                self._tokens.fingerprint(session_token)
            )
        if session is None or not session.is_active_at(now):
            raise SessionRequiredError("Требуется действующая демонстрационная сессия.")
        return ActorContext(
            user_id=session.user_id,
            session_id=session.session_id,
            namespace_id=session.manual_namespace_id,
            roles=frozenset(ActorRole(role.value) for role in session.roles),
            consent_revision=session.consent_revision,
            execution_mode=self._execution_mode,
        )

    def update_consent(
        self,
        *,
        actor: ActorContext,
        idempotency_key: str,
        scope: ConsentScope,
        status: ConsentStatus,
        expected_revision: int,
    ) -> ConsentView:
        now = self._clock.now_utc()
        command = {
            "scope": scope.value,
            "status": status.value,
            "expected_revision": expected_revision,
        }
        idempotency_scope = IdempotencyScope(
            principal_fingerprint=self._tokens.fingerprint_principal(["actor", str(actor.user_id)]),
            session_id=actor.session_id,
            namespace_id=actor.namespace_id,
            method="PATCH",
            canonical_route="/api/v1/consents/{scope}",
            key=idempotency_key,
        )
        candidate = IdempotencyRecord(
            record_id=self._id_generator.new_id(),
            scope=idempotency_scope,
            command_hash=self._tokens.fingerprint_command(command),
            resource_id=actor.user_id,
            state=IdempotencyState.IN_PROGRESS,
            result=None,
            revision=0,
            created_at=now,
            updated_at=now,
        )
        with self._unit_of_work() as uow:
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                return self._replay_consent(reservation.record)
            session = uow.identity.get_session(actor.session_id)
            if (
                session is None
                or session.user_id != actor.user_id
                or session.manual_namespace_id != actor.namespace_id
                or not session.is_active_at(now)
            ):
                raise SessionRequiredError("Требуется действующая демонстрационная сессия.")
            if expected_revision != session.consent_revision:
                raise StaleRevisionError("Версия согласий устарела.")
            consent = uow.identity.get_consent(actor.user_id, scope)
            if consent is None:
                raise ServiceUnavailableError("Consent storage is incomplete")

            updated = consent
            if consent.status is not status:
                advanced_session = session.advance_consent_revision(
                    expected_revision=expected_revision
                )
                updated = consent.change(
                    status,
                    revision=advanced_session.consent_revision,
                    changed_at=now,
                )
                uow.identity.save_session(
                    advanced_session,
                    expected_consent_revision=session.consent_revision,
                )
                uow.identity.save_consent(updated, expected_revision=consent.revision)
                uow.audit.append(
                    self._audit_record(
                        event_type="consent.changed",
                        aggregate_id=actor.user_id,
                        aggregate_revision=updated.revision,
                        correlation_id=actor.session_id,
                        payload={
                            "scope": updated.scope.value,
                            "status": updated.status.value,
                            "revision": updated.revision,
                        },
                        actor_id=actor.user_id,
                        session_id=actor.session_id,
                        namespace_id=actor.namespace_id,
                        now=now,
                    )
                )
            result = self._consent_result(updated)
            uow.idempotency.save(
                reservation.record.finish(
                    state=IdempotencyState.COMPLETED,
                    result=result,
                    updated_at=now,
                ),
                expected_revision=0,
            )
            uow.commit()
        return ConsentView.from_snapshot(updated)

    def _session_view(
        self,
        repository: IdentityRepositoryPort,
        session: DemoSession,
    ) -> SessionView:
        consents = repository.list_consents(session.user_id)
        if {item.scope for item in consents} != set(ConsentScope):
            raise ServiceUnavailableError("Consent storage is incomplete")
        return SessionView.from_session(
            session,
            consents,
            execution_mode=self._execution_mode,
        )

    def _replay_start(
        self,
        repository: IdentityRepositoryPort,
        record: IdempotencyRecord,
        *,
        pre_session: PreSession | None,
        pre_session_token: str,
        now: datetime,
    ) -> StartSessionResult:
        if record.state is IdempotencyState.IN_PROGRESS:
            raise ActionInProgressError("Создание сессии еще выполняется.")
        if record.state is not IdempotencyState.COMPLETED:
            raise ServiceUnavailableError("Session creation did not complete")
        if (
            pre_session is None
            or pre_session.consumed_session_id != record.resource_id
            or now >= pre_session.expires_at
        ):
            raise SessionRequiredError("Pre-session token is no longer valid")
        session = repository.get_session(record.resource_id)
        if session is None or not session.is_active_at(now):
            raise ServiceUnavailableError("Stored session is unavailable")
        session_token = self._tokens.derive_session_token(pre_session_token, session.session_id)
        return StartSessionResult(
            view=self._session_view(repository, session),
            session_token=session_token,
            csrf_token=self._tokens.derive_csrf_token(session_token),
            replayed=True,
        )

    @staticmethod
    def _consent_result(consent: ConsentSnapshot) -> dict[str, str | int]:
        return {
            "scope": consent.scope.value,
            "status": consent.status.value,
            "revision": consent.revision,
            "changed_at": consent.changed_at.isoformat(),
        }

    @staticmethod
    def _replay_consent(record: IdempotencyRecord) -> ConsentView:
        if record.state is IdempotencyState.IN_PROGRESS:
            raise ActionInProgressError("Изменение согласия еще выполняется.")
        if record.state is not IdempotencyState.COMPLETED or record.result is None:
            raise ServiceUnavailableError("Consent update did not complete")
        result = record.result
        try:
            revision = result["revision"]
            if isinstance(revision, bool) or not isinstance(revision, int):
                raise TypeError("revision is not an integer")
            return ConsentView(
                scope=ConsentScope(str(result["scope"])),
                status=ConsentStatus(str(result["status"])),
                revision=revision,
                changed_at=datetime.fromisoformat(str(result["changed_at"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceUnavailableError("Stored consent result is invalid") from exc

    def _audit_record(
        self,
        *,
        event_type: str,
        aggregate_id: EntityId,
        aggregate_revision: int,
        correlation_id: EntityId,
        payload: dict[str, str | int],
        actor_id: EntityId,
        session_id: EntityId,
        namespace_id: EntityId,
        now: datetime,
    ) -> AuditRecord:
        event = EventEnvelope(
            event_id=self._id_generator.new_id(),
            event_type=event_type,
            aggregate_id=aggregate_id,
            aggregate_revision=aggregate_revision,
            occurred_at=now,
            correlation_id=correlation_id,
            causation_id=None,
            execution_mode=self._execution_mode,
            payload=payload,
        )
        return AuditRecord(
            event=event,
            actor_id=actor_id,
            session_id=session_id,
            namespace_id=namespace_id,
            recorded_at=now,
        )
