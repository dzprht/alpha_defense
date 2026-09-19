"""Readiness checks for the local database and mandatory content catalog."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from alpha_defense.application.ports import ReadinessCheck, ReadinessReport

EXPECTED_SCHEMA_REVISION = "20260918_0002"


class LocalReadinessChecker:
    """Report only stable check codes; never expose paths or driver errors."""

    def __init__(self, engine: Engine, policy_file: Path) -> None:
        self._engine = engine
        self._policy_file = policy_file

    def check(self) -> ReadinessReport:
        return ReadinessReport(
            checks=(
                self._check_database(),
                self._check_policy_catalog(),
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

    def _check_policy_catalog(self) -> ReadinessCheck:
        try:
            available = self._policy_file.is_file()
        except OSError:
            available = False
        code = "ready" if available else "catalog_unavailable"
        return ReadinessCheck("policy_catalog", available, code)
