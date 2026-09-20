"""Catalog, bootstrap, SQLite, and restart integration for P09."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa

from alpha_defense.bootstrap import build_container
from alpha_defense.domain.communications import SmsPayload
from alpha_defense.transport.http.v1.schemas import ObservationInputSchema
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def test_s01_observation_is_ingested_once_and_restored_with_raw_content(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "app.db"
    migrate(database_path)
    settings = make_settings(tmp_path)
    first_container = build_container(settings)
    bootstrap = first_container.identity_service.bootstrap_session(
        session_token=None,
        pre_session_token=None,
    )
    assert bootstrap.pre_session_token is not None
    started = first_container.identity_service.start_session(
        pre_session_token=bootstrap.pre_session_token,
        idempotency_key="start-p09-session",
        profile_code="demo-user",
    )
    actor = first_container.identity_service.resolve_actor(started.session_token)
    fixture = next(
        item
        for item in first_container.catalog.load().fixtures
        if item.fixture_id == "s01-card-block-sms"
    )
    request = dict(fixture.payload)
    source = request.pop("source")
    assert isinstance(source, str)
    observation_input = ObservationInputSchema.model_validate(request).to_input()
    assert isinstance(observation_input.payload, SmsPayload)

    created = first_container.ingest_observation.execute(
        actor=actor,
        source=source,
        observation_input=observation_input,
    )
    observation_id = created.observation.observation_id
    with first_container.engine.connect() as connection:
        observation_columns = {
            item[1] for item in connection.execute(sa.text("PRAGMA table_info(observations)"))
        }
        raw_payload = connection.execute(
            sa.text("SELECT payload_json FROM observation_content WHERE observation_id = :id"),
            {"id": str(observation_id)},
        ).scalar_one()
    first_container.close()

    second_container = build_container(settings)
    restored = second_container.get_observation.execute(
        actor=actor,
        observation_id=observation_id,
    )
    repeated = second_container.ingest_observation.execute(
        actor=actor,
        source=source,
        observation_input=observation_input,
    )
    second_container.close()

    assert not created.duplicate
    assert repeated.duplicate
    assert repeated.observation.observation_id == observation_id
    assert "text" not in observation_columns
    assert isinstance(raw_payload, str)
    assert "Ваша карта заблокирована" in raw_payload
    assert isinstance(restored.payload, SmsPayload)
    assert restored.payload.text == observation_input.payload.text
    assert [item.normalized_value for item in restored.normalized_indicators[1:]] == [
        "https://alfa-secure-check.test/card",
        "alfa-secure-check.test",
    ]
