"""Readiness checks for the local database and mandatory content catalog."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from alpha_defense.application.ports import (
    CatalogLoaderPort,
    ReadinessCheck,
    ReadinessReport,
)

EXPECTED_SCHEMA_REVISION = "20260926_0009"


class LocalReadinessChecker:
    """Report only stable check codes; never expose paths or driver errors."""

    def __init__(self, engine: Engine, catalog: CatalogLoaderPort) -> None:
        self._engine = engine
        self._catalog = catalog

    def check(self) -> ReadinessReport:
        return ReadinessReport(
            checks=(
                self._check_database(),
                self._check_catalog(),
            )
        )

    def _check_database(self) -> ReadinessCheck:
        try:
            with self._engine.connect() as connection:
                connection.execute(sa.text("SELECT 1"))
                revision = connection.execute(
                    sa.text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
        except (SQLAlchemyError, OSError):
            return ReadinessCheck("database", False, "storage_unavailable")
        if revision != EXPECTED_SCHEMA_REVISION:
            return ReadinessCheck("database", False, "schema_outdated")
        return ReadinessCheck("database", True, "ready")

    def _check_catalog(self) -> ReadinessCheck:
        try:
            self._catalog.load()
        except (OSError, ValueError):
            return ReadinessCheck("catalog", False, "catalog_unavailable")
        return ReadinessCheck("catalog", True, "ready")
