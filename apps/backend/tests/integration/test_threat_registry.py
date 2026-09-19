"""Fixture feed, bootstrap, SQLite, and restart integration for P08."""

from __future__ import annotations

from pathlib import Path

from alpha_defense.application.threats import RegistryAvailability, ThreatLookupOutcome
from alpha_defense.bootstrap import build_container
from alpha_defense.domain.threats import IndicatorType, ThreatIndicator
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def test_fixture_registry_seed_is_idempotent_and_survives_restart(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "app.db"
    migrate(database_path)
    settings = make_settings(tmp_path)
    first_container = build_container(settings)

    first = first_container.refresh_threat_registry.execute()
    repeated = first_container.refresh_threat_registry.execute()
    lookup = first_container.lookup_threats.execute(
        (
            ThreatIndicator.from_raw(
                IndicatorType.URL,
                "https://alfa-secure-check.test/card",
            ),
        )
    )[0]
    first_container.close()

    second_container = build_container(settings)
    restored = second_container.threat_registry_status.execute()
    second_container.close()

    assert first.published
    assert not repeated.published
    assert first.record_count == 1
    assert lookup.outcome is ThreatLookupOutcome.MATCH
    assert lookup.snapshot_version == first.snapshot_version
    assert restored.availability is RegistryAvailability.READY
    assert restored.snapshot_version == first.snapshot_version
