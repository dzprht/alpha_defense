"""Composition of concrete adapters after configuration validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from alpha_defense.application.communications import GetObservation, IngestObservation
from alpha_defense.application.identity import IdentityService, IdentityServicePort
from alpha_defense.application.ports import (
    CatalogLoaderPort,
    Clock,
    IdGenerator,
    ReadinessPort,
    UnitOfWorkFactory,
)
from alpha_defense.application.threats import (
    GetThreatRegistryStatus,
    LookupThreatIndicators,
    RefreshThreatRegistry,
)
from alpha_defense.bootstrap.settings import Settings
from alpha_defense.domain.shared import ExecutionMode
from alpha_defense.infrastructure.content import LocalCatalogLoader
from alpha_defense.infrastructure.identity.mock import HmacSecurityTokens, SyntheticIdentityProvider
from alpha_defense.infrastructure.observability import (
    EXPECTED_SCHEMA_REVISION,
    LocalReadinessChecker,
)
from alpha_defense.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyUnitOfWorkFactory,
    create_sqlite_engine,
)
from alpha_defense.infrastructure.runtime import SystemClock, UuidGenerator
from alpha_defense.infrastructure.threat_intel import FixtureThreatFeed


class ConfigurationError(RuntimeError):
    """Safe startup failure whose message contains no secret or connection string."""


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: Engine
    unit_of_work: UnitOfWorkFactory
    clock: Clock
    id_generator: IdGenerator
    readiness: ReadinessPort
    catalog: CatalogLoaderPort
    identity_service: IdentityServicePort
    lookup_threats: LookupThreatIndicators
    refresh_threat_registry: RefreshThreatRegistry
    threat_registry_status: GetThreatRegistryStatus
    ingest_observation: IngestObservation
    get_observation: GetObservation

    def close(self) -> None:
        self.engine.dispose()


def build_container(settings: Settings) -> Container:
    """Validate mandatory local capabilities and build the runtime graph."""

    if settings.execution_mode is not ExecutionMode.MOCK:
        raise ConfigurationError("Live execution mode has no verified adapters")
    _require_directory(settings.schema_root, "SCHEMA_ROOT")
    _require_directory(settings.content_root, "CONTENT_ROOT")
    _require_directory(settings.fixture_root, "FIXTURE_ROOT")
    _require_directory(settings.media_root, "MEDIA_ROOT")
    database_path = _sqlite_path(settings.database_url)
    if not database_path.is_file():
        raise ConfigurationError("DATABASE_URL must point to an existing migrated database")

    engine = create_sqlite_engine(database_path)
    try:
        _verify_database(engine)
    except ConfigurationError:
        engine.dispose()
        raise
    factory = SqlAlchemyUnitOfWorkFactory(engine)
    clock = SystemClock()
    id_generator = UuidGenerator()
    catalog = LocalCatalogLoader(
        schema_root=settings.schema_root,
        content_root=settings.content_root,
        fixture_root=settings.fixture_root,
        policy_version=settings.policy_version,
    )
    threat_feed = FixtureThreatFeed(catalog)
    identity_service = IdentityService(
        unit_of_work=factory,
        clock=clock,
        id_generator=id_generator,
        provider=SyntheticIdentityProvider(),
        tokens=HmacSecurityTokens(settings.session_secret.get_secret_value()),
        execution_mode=settings.execution_mode,
    )
    return Container(
        settings=settings,
        engine=engine,
        unit_of_work=factory,
        clock=clock,
        id_generator=id_generator,
        readiness=LocalReadinessChecker(engine, catalog),
        catalog=catalog,
        identity_service=identity_service,
        lookup_threats=LookupThreatIndicators(unit_of_work=factory, clock=clock),
        refresh_threat_registry=RefreshThreatRegistry(
            source=settings.threat_feed_source,
            feed=threat_feed,
            unit_of_work=factory,
            clock=clock,
            id_generator=id_generator,
            execution_mode=settings.execution_mode,
        ),
        threat_registry_status=GetThreatRegistryStatus(
            unit_of_work=factory,
            clock=clock,
        ),
        ingest_observation=IngestObservation(
            unit_of_work=factory,
            clock=clock,
            id_generator=id_generator,
        ),
        get_observation=GetObservation(unit_of_work=factory),
    )


def _require_directory(path: Path, setting_name: str) -> None:
    try:
        valid = path.is_dir()
    except OSError:
        valid = False
    if not valid:
        raise ConfigurationError(f"{setting_name} must point to an existing directory")


def _sqlite_path(database_url: str) -> Path:
    try:
        url = make_url(database_url)
    except (sa.exc.ArgumentError, TypeError) as exc:
        raise ConfigurationError("DATABASE_URL is invalid") from exc
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ConfigurationError("Only a file-backed SQLite DATABASE_URL is supported")
    return Path(url.database).expanduser().resolve()


def _verify_database(engine: Engine) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
            revision = connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    except (SQLAlchemyError, OSError) as exc:
        raise ConfigurationError("Database is unavailable or has no managed schema") from exc
    if revision != EXPECTED_SCHEMA_REVISION:
        raise ConfigurationError("Database schema is not at the required revision")
