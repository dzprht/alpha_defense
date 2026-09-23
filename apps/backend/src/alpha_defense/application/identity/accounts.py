"""Account lifecycle with persistent ownership and session-bound command replay."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from alpha_defense.application.identity.dto import SessionView, StartSessionResult
from alpha_defense.application.identity.ports import (
    AccountServicePort,
    CredentialPort,
    IdentityUnitOfWorkFactory,
    IdentityUnitOfWorkPort,
    SecurityTokenPort,
)
from alpha_defense.application.identity.service import SESSION_TTL
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
    InvalidCredentialsError,
    RateLimitedError,
    ServiceUnavailableError,
    SessionRequiredError,
    ValidationError,
)
from alpha_defense.domain.identity import (
    Account,
    AccountStatus,
    ConsentScope,
    ConsentSnapshot,
    ConsentStatus,
    DemoSession,
    LoginThrottle,
    SessionAuthKind,
    SessionRole,
    SyntheticUser,
    normalize_login,
)
from alpha_defense.domain.shared import ExecutionMode

LOGIN_WINDOW = timedelta(minutes=15)
MAX_LOGIN_FAILURES = 5


class AccountService(AccountServicePort):
    def __init__(
        self,
        unit_of_work: IdentityUnitOfWorkFactory,
        clock: Clock,
        id_generator: IdGenerator,
        credentials: CredentialPort,
        tokens: SecurityTokenPort,
        execution_mode: ExecutionMode,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_generator = id_generator
        self._credentials = credentials
        self._tokens = tokens
        self._execution_mode = execution_mode

    def register(
        self,
        *,
        pre_session_token: str,
        idempotency_key: str,
        login: str,
        password: str,
    ) -> StartSessionResult:
        normalized = self._validate_credentials(login, password)
        password_hash = self._credentials.hash_password(password)
        now = self._clock.now_utc()
        candidate = self._candidate(
            token=pre_session_token,
            key=idempotency_key,
            route="/api/v1/accounts",
            command_hash=self._tokens.fingerprint_credentials(normalized, password),
            now=now,
        )
        with self._unit_of_work() as uow:
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                return self._replay(uow, reservation.record, pre_session_token, now)
            self._require_pre_session(uow, pre_session_token, now)
            if uow.accounts.get_by_login(normalized) is not None:
                raise ValidationError("Логин уже занят.")
            account = Account(
                user_id=self._id_generator.new_id(),
                normalized_login=normalized,
                password_hash=password_hash,
                namespace_id=self._id_generator.new_id(),
                status=AccountStatus.ACTIVE,
                consent_revision=0,
                created_at=now,
            )
            uow.identity.add_user(
                SyntheticUser(
                    user_id=account.user_id,
                    profile_code="account-owner",
                    created_at=now,
                )
            )
            uow.accounts.add(account)
            for scope in ConsentScope:
                uow.identity.add_consent(
                    ConsentSnapshot(
                        user_id=account.user_id,
                        scope=scope,
                        status=ConsentStatus.REVOKED,
                        revision=0,
                        changed_at=now,
                    )
                )
            session, token = self._start_session(
                uow, account, reservation.record, pre_session_token, now
            )
            self._audit(uow, "account.registered", session, now)
            self._finish(uow, reservation.record, now)
            result = self._result(uow, session, token, replayed=False)
            uow.commit()
            return result

    def login(
        self,
        *,
        pre_session_token: str,
        idempotency_key: str,
        login: str,
        password: str,
    ) -> StartSessionResult:
        normalized = self._validate_credentials(login, password)
        now = self._clock.now_utc()
        candidate = self._candidate(
            token=pre_session_token,
            key=idempotency_key,
            route="/api/v1/sessions",
            command_hash=self._tokens.fingerprint_credentials(normalized, password),
            now=now,
        )
        # Verification is deliberately outside the write transaction.
        with self._unit_of_work() as read:
            account = read.accounts.get_by_login(normalized)
            hash_to_verify = None if account is None else account.password_hash
        valid_password = self._credentials.verify_password(hash_to_verify, password)
        outcome: str | None = None
        with self._unit_of_work() as uow:
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                return self._replay(uow, reservation.record, pre_session_token, now)
            self._require_pre_session(uow, pre_session_token, now)
            current = uow.accounts.get_by_login(normalized)
            fingerprint = self._tokens.fingerprint_login(normalized)
            throttle = uow.accounts.get_throttle(fingerprint)
            if throttle is not None and throttle.is_blocked_at(now):
                outcome = "rate_limited"
            elif (
                current is None
                or current.status is not AccountStatus.ACTIVE
                or not valid_password
                or current.password_hash != hash_to_verify
            ):
                outcome = "invalid_credentials"
                self._record_failure(uow, fingerprint, throttle, now)
            else:
                self._clear_failure(uow, throttle, now)
                session, token = self._start_session(
                    uow,
                    current,
                    reservation.record,
                    pre_session_token,
                    now,
                )
                self._audit(uow, "account.logged_in", session, now)
                self._finish(uow, reservation.record, now)
                result = self._result(uow, session, token, replayed=False)
                uow.commit()
                return result
            self._finish(uow, reservation.record, now, error=outcome)
            uow.commit()
        self._raise_login_error(outcome)
        raise AssertionError("unreachable")

    def logout(self, *, session_token: str, idempotency_key: str) -> None:
        now = self._clock.now_utc()
        fingerprint = self._tokens.fingerprint(session_token)
        candidate = self._candidate(
            token=session_token,
            key=idempotency_key,
            route="/api/v1/sessions/logout",
            command_hash=self._tokens.fingerprint_command({"action": "logout"}),
            now=now,
        )
        with self._unit_of_work() as uow:
            reservation = uow.idempotency.reserve(candidate)
            if not reservation.is_new:
                if reservation.record.state is IdempotencyState.COMPLETED:
                    return
                raise ActionInProgressError("Завершение сессии еще выполняется.")
            session = uow.identity.get_session_by_fingerprint(fingerprint)
            if session is None or not session.is_active_at(now):
                raise SessionRequiredError("Требуется действующая сессия.")
            uow.identity.revoke_session(session.revoke(at=now))
            event_type = (
                "account.logged_out"
                if session.auth_kind is SessionAuthKind.ACCOUNT
                else "session.logged_out"
            )
            self._audit(uow, event_type, session, now)
            self._finish(uow, reservation.record, now)
            uow.commit()

    @staticmethod
    def _validate_credentials(login: str, password: str) -> str:
        try:
            normalized = normalize_login(login)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Логин должен содержать от 3 до 64 латинских символов, цифры и разделители."
            ) from exc
        if (
            not isinstance(password, str)
            or not 12 <= len(password) <= 128
            or len(password.encode("utf-8")) > 512
            or "\x00" in password
        ):
            raise ValidationError("Пароль должен содержать от 12 до 128 символов.")
        return normalized

    def _candidate(
        self,
        *,
        token: str,
        key: str,
        route: str,
        command_hash: str,
        now: datetime,
    ) -> IdempotencyRecord:
        return IdempotencyRecord(
            record_id=self._id_generator.new_id(),
            scope=IdempotencyScope(
                principal_fingerprint=self._tokens.fingerprint(token),
                method="POST",
                canonical_route=route,
                key=key,
            ),
            command_hash=command_hash,
            resource_id=self._id_generator.new_id(),
            state=IdempotencyState.IN_PROGRESS,
            result=None,
            revision=0,
            created_at=now,
            updated_at=now,
        )

    def _require_pre_session(
        self,
        uow: IdentityUnitOfWorkPort,
        token: str,
        now: datetime,
    ) -> None:
        pre = uow.identity.get_pre_session_by_fingerprint(self._tokens.fingerprint(token))
        if pre is None or not pre.is_available_at(now):
            raise SessionRequiredError("Сначала получите pre-session через GET /session.")

    def _start_session(
        self,
        uow: IdentityUnitOfWorkPort,
        account: Account,
        record: IdempotencyRecord,
        pre_token: str,
        now: datetime,
    ) -> tuple[DemoSession, str]:
        session_id = record.resource_id
        token = self._tokens.derive_session_token(pre_token, session_id)
        session = DemoSession(
            session_id=session_id,
            user_id=account.user_id,
            manual_namespace_id=self._id_generator.new_id(),
            roles=frozenset({SessionRole.DEMO_USER}),
            token_fingerprint=self._tokens.fingerprint(token),
            consent_revision=account.consent_revision,
            created_at=now,
            expires_at=now + SESSION_TTL,
            auth_kind=SessionAuthKind.ACCOUNT,
            workspace_namespace_id=account.namespace_id,
        )
        pre = uow.identity.get_pre_session_by_fingerprint(self._tokens.fingerprint(pre_token))
        if pre is None:
            raise SessionRequiredError("Pre-session отсутствует.")
        uow.identity.add_session(session)
        uow.identity.save_pre_session(
            pre.consume(session_id, now=now), expected_consumed_session_id=None
        )
        return session, token

    def _result(
        self,
        uow: IdentityUnitOfWorkPort,
        session: DemoSession,
        token: str,
        *,
        replayed: bool,
    ) -> StartSessionResult:
        account = uow.accounts.get_by_id(session.user_id)
        if account is None:
            raise ServiceUnavailableError("Account is missing")
        consents = uow.identity.list_consents(session.user_id)
        if {item.scope for item in consents} != set(ConsentScope):
            raise ServiceUnavailableError("Consent storage is incomplete")
        return StartSessionResult(
            view=SessionView.from_session(
                session,
                consents,
                execution_mode=self._execution_mode,
                consent_revision=account.consent_revision,
            ),
            session_token=token,
            csrf_token=self._tokens.derive_csrf_token(token),
            replayed=replayed,
        )

    def _replay(
        self,
        uow: IdentityUnitOfWorkPort,
        record: IdempotencyRecord,
        pre_token: str,
        now: datetime,
    ) -> StartSessionResult:
        if record.state is IdempotencyState.IN_PROGRESS:
            raise ActionInProgressError("Команда еще выполняется.")
        if record.state is IdempotencyState.FAILED:
            error = None if record.result is None else record.result.get("error")
            self._raise_login_error(error if isinstance(error, str) else None)
        pre = uow.identity.get_pre_session_by_fingerprint(self._tokens.fingerprint(pre_token))
        if pre is None or pre.consumed_session_id != record.resource_id or now >= pre.expires_at:
            raise SessionRequiredError("Pre-session token is no longer valid")
        session = uow.identity.get_session(record.resource_id)
        if session is None or not session.is_active_at(now):
            raise SessionRequiredError("Сессия больше не активна.")
        token = self._tokens.derive_session_token(pre_token, session.session_id)
        return self._result(uow, session, token, replayed=True)

    def _record_failure(
        self,
        uow: IdentityUnitOfWorkPort,
        fingerprint: str,
        throttle: LoginThrottle | None,
        now: datetime,
    ) -> None:
        if throttle is None:
            uow.accounts.add_throttle(LoginThrottle(fingerprint, 1, now, None, 0))
            return
        if now >= throttle.window_started_at + LOGIN_WINDOW:
            failures, window_start = 1, now
        else:
            failures, window_start = throttle.failures + 1, throttle.window_started_at
        uow.accounts.save_throttle(
            replace(
                throttle,
                failures=failures,
                window_started_at=window_start,
                blocked_until=now + LOGIN_WINDOW if failures >= MAX_LOGIN_FAILURES else None,
                revision=throttle.revision + 1,
            ),
            expected_revision=throttle.revision,
        )

    def _clear_failure(
        self,
        uow: IdentityUnitOfWorkPort,
        throttle: LoginThrottle | None,
        now: datetime,
    ) -> None:
        if throttle is not None:
            uow.accounts.save_throttle(
                replace(
                    throttle,
                    failures=0,
                    window_started_at=now,
                    blocked_until=None,
                    revision=throttle.revision + 1,
                ),
                expected_revision=throttle.revision,
            )

    @staticmethod
    def _raise_login_error(error: str | None) -> None:
        if error == "rate_limited":
            raise RateLimitedError("Слишком много попыток входа. Повторите через 15 минут.")
        raise InvalidCredentialsError("Неверный логин или пароль.")

    @staticmethod
    def _finish(
        uow: IdentityUnitOfWorkPort,
        record: IdempotencyRecord,
        now: datetime,
        error: str | None = None,
    ) -> None:
        uow.idempotency.save(
            record.finish(
                state=IdempotencyState.FAILED if error is not None else IdempotencyState.COMPLETED,
                result={"error": error}
                if error is not None
                else {"session_id": str(record.resource_id)},
                updated_at=now,
            ),
            expected_revision=0,
        )

    def _audit(
        self,
        uow: IdentityUnitOfWorkPort,
        event_type: str,
        session: DemoSession,
        now: datetime,
    ) -> None:
        uow.audit.append(
            AuditRecord(
                event=EventEnvelope(
                    event_id=self._id_generator.new_id(),
                    event_type=event_type,
                    aggregate_id=session.user_id,
                    aggregate_revision=0,
                    occurred_at=now,
                    correlation_id=session.session_id,
                    causation_id=None,
                    execution_mode=self._execution_mode,
                    payload={"auth_kind": session.auth_kind.value},
                ),
                actor_id=session.user_id,
                session_id=session.session_id,
                namespace_id=session.namespace_id,
                recorded_at=now,
            )
        )
