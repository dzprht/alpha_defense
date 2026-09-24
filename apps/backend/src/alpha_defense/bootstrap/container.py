"""Composition of concrete adapters after configuration validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from alpha_defense.application.communications import GetObservation, IngestObservation
from alpha_defense.application.detection import AssessObservation
from alpha_defense.application.education import GetCard, GetGuidance, ListCards
from alpha_defense.application.identity import (
    AccountService,
    AccountServicePort,
    IdentityService,
    IdentityServicePort,
)
from alpha_defense.application.incidents import AttachObservation, GetIncident, ResolveIncident
from alpha_defense.application.ports import (
    CatalogLoaderPort,
    Clock,
    IdGenerator,
    ReadinessPort,
    UnitOfWorkFactory,
)
from alpha_defense.application.protection import WarningService
from alpha_defense.application.threats import (
    GetThreatRegistryStatus,
    LookupThreatIndicators,
    RefreshThreatRegistry,
)
from alpha_defense.application.workflows import AnalyzeContact, PublishWarning
from alpha_defense.bootstrap.settings import Settings
from alpha_defense.domain.shared import ExecutionMode
from alpha_defense.infrastructure.analysis.ml import LocalTextModelAnalyzer
from alpha_defense.infrastructure.analysis.mock import (
    DeterministicTextAnalyzer,
    DeterministicUrlAnalyzer,
)
from alpha_defense.infrastructure.content import LocalCatalogLoader
from alpha_defense.infrastructure.identity.credentials import Argon2Credentials
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
    account_service: AccountServicePort
    lookup_threats: LookupThreatIndicators
    refresh_threat_registry: RefreshThreatRegistry
    threat_registry_status: GetThreatRegistryStatus
    ingest_observation: IngestObservation
    get_observation: GetObservation
    attach_observation: AttachObservation
    get_incident: GetIncident
    resolve_incident: ResolveIncident
    analyze_contact: AnalyzeContact
    assess_observation: AssessObservation
    get_guidance: GetGuidance
    warnings: WarningService
    publish_warning: PublishWarning
    list_cards: ListCards
    get_card: GetCard

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
    text_model = None
    if settings.policy_version == "demo-risk-v2":
        if settings.model_root is None:
            raise ConfigurationError("MODEL_ROOT is required for the model-enabled policy")
        _require_directory(settings.model_root, "MODEL_ROOT")
        try:
            text_model = LocalTextModelAnalyzer.from_trusted_directory(settings.model_root)
        except Exception as exc:
            raise ConfigurationError("MODEL_ROOT contains no valid trusted text model") from exc
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
    tokens = HmacSecurityTokens(settings.session_secret.get_secret_value())
    identity_service = IdentityService(
        unit_of_work=factory,
        clock=clock,
        id_generator=id_generator,
        provider=SyntheticIdentityProvider(),
        tokens=tokens,
        execution_mode=settings.execution_mode,
    )
    account_service = AccountService(
        unit_of_work=factory,
        clock=clock,
        id_generator=id_generator,
        credentials=Argon2Credentials(),
        tokens=tokens,
        execution_mode=settings.execution_mode,
    )
    ingest_observation = IngestObservation(
        unit_of_work=factory,
        clock=clock,
        id_generator=id_generator,
    )
    attach_observation = AttachObservation(
        unit_of_work=factory,
        clock=clock,
        id_generator=id_generator,
    )
    guidance = GetGuidance(catalog)
    warnings = WarningService(unit_of_work=factory, clock=clock, id_generator=id_generator)
    return Container(
        settings=settings,
        engine=engine,
        unit_of_work=factory,
        clock=clock,
        id_generator=id_generator,
        readiness=LocalReadinessChecker(engine, catalog),
        catalog=catalog,
        identity_service=identity_service,
        account_service=account_service,
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
        ingest_observation=ingest_observation,
        get_observation=GetObservation(unit_of_work=factory),
        attach_observation=attach_observation,
        get_incident=GetIncident(unit_of_work=factory),
        resolve_incident=ResolveIncident(
            unit_of_work=factory,
            clock=clock,
            id_generator=id_generator,
        ),
        analyze_contact=AnalyzeContact(
            unit_of_work=factory,
            ingest_observation=ingest_observation,
            attach_observation=attach_observation,
        ),
        assess_observation=AssessObservation(
            catalog=catalog,
            text_analyzer=DeterministicTextAnalyzer(),
            text_model_analyzer=text_model,
            resource_analyzer=DeterministicUrlAnalyzer(),
            clock=clock,
            id_generator=id_generator,
        ),
        get_guidance=guidance,
        warnings=warnings,
        publish_warning=PublishWarning(guidance=guidance, warnings=warnings),
        list_cards=ListCards(catalog),
        get_card=GetCard(catalog),
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
