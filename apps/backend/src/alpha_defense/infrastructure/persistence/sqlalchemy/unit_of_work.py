"""SQLAlchemy transaction boundary for the SQLite adapter."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alpha_defense.application.shared import ServiceUnavailableError
from alpha_defense.infrastructure.persistence.sqlalchemy.communications import (
    SqlAlchemyObservationRepository,
)
from alpha_defense.infrastructure.persistence.sqlalchemy.incidents import (
    SqlAlchemyIncidentRepository,
    SqlAlchemyNamespaceRiskStateRepository,
)
from alpha_defense.infrastructure.persistence.sqlalchemy.protection import (
    SqlAlchemyWarningRepository,
)
from alpha_defense.infrastructure.persistence.sqlalchemy.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyAuditRepository,
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyIdentityRepository,
    SqlAlchemyOutboxRepository,
)
from alpha_defense.infrastructure.persistence.sqlalchemy.threat_registry import (
    SqlAlchemyThreatRegistryRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name != "sqlite":
            raise ValueError("P03 SqlAlchemyUnitOfWork supports SQLite only")
        self._engine = engine
        self._session: Session | None = None
        self._active = False
        self._finished = False
        self._idempotency: SqlAlchemyIdempotencyRepository | None = None
        self._identity: SqlAlchemyIdentityRepository | None = None
        self._accounts: SqlAlchemyAccountRepository | None = None
        self._audit: SqlAlchemyAuditRepository | None = None
        self._outbox: SqlAlchemyOutboxRepository | None = None
        self._threat_registry: SqlAlchemyThreatRegistryRepository | None = None
        self._observations: SqlAlchemyObservationRepository | None = None
        self._incidents: SqlAlchemyIncidentRepository | None = None
        self._namespace_risk_states: SqlAlchemyNamespaceRiskStateRepository | None = None
        self._warnings: SqlAlchemyWarningRepository | None = None

    @property
    def idempotency(self) -> SqlAlchemyIdempotencyRepository:
        if self._idempotency is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._idempotency

    @property
    def audit(self) -> SqlAlchemyAuditRepository:
        if self._audit is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._audit

    @property
    def identity(self) -> SqlAlchemyIdentityRepository:
        if self._identity is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._identity

    @property
    def accounts(self) -> SqlAlchemyAccountRepository:
        if self._accounts is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._accounts

    @property
    def outbox(self) -> SqlAlchemyOutboxRepository:
        if self._outbox is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._outbox

    @property
    def threat_registry(self) -> SqlAlchemyThreatRegistryRepository:
        if self._threat_registry is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._threat_registry

    @property
    def observations(self) -> SqlAlchemyObservationRepository:
        if self._observations is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._observations

    @property
    def incidents(self) -> SqlAlchemyIncidentRepository:
        if self._incidents is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._incidents

    @property
    def namespace_risk_states(self) -> SqlAlchemyNamespaceRiskStateRepository:
        if self._namespace_risk_states is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._namespace_risk_states

    @property
    def warnings(self) -> SqlAlchemyWarningRepository:
        if self._warnings is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._warnings

    def begin(self) -> None:
        if self._active:
            raise RuntimeError("UnitOfWork is already active")
        self._session = Session(self._engine, expire_on_commit=False)
        self._session.begin()
        self._idempotency = SqlAlchemyIdempotencyRepository(self._session)
        self._identity = SqlAlchemyIdentityRepository(self._session)
        self._accounts = SqlAlchemyAccountRepository(self._session)
        self._audit = SqlAlchemyAuditRepository(self._session)
        self._outbox = SqlAlchemyOutboxRepository(self._session)
        self._threat_registry = SqlAlchemyThreatRegistryRepository(self._session)
        self._observations = SqlAlchemyObservationRepository(self._session)
        self._incidents = SqlAlchemyIncidentRepository(self._session)
        self._namespace_risk_states = SqlAlchemyNamespaceRiskStateRepository(self._session)
        self._warnings = SqlAlchemyWarningRepository(self._session)
        self._active = True
        self._finished = False

    def commit(self) -> None:
        session = self._require_unfinished()
        try:
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise ServiceUnavailableError("Local persistence commit failed") from exc
        finally:
            self._finished = True

    def rollback(self) -> None:
        session = self._require_active()
        if not self._finished:
            session.rollback()
            self._finished = True

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.begin()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._active and not self._finished:
            self.rollback()
        if self._session is not None:
            self._session.close()
        self._active = False

    def _require_active(self) -> Session:
        if not self._active or self._session is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._session

    def _require_unfinished(self) -> Session:
        session = self._require_active()
        if self._finished:
            raise RuntimeError("UnitOfWork transaction is already finished")
        return session


class SqlAlchemyUnitOfWorkFactory:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def __call__(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.engine)
