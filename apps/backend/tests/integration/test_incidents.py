"""Bootstrap, SQLite, and restart integration for P10 incident intake."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import cast

from alpha_defense.application.communications import ObservationInput, SmsPayload
from alpha_defense.application.ports import IncidentUnitOfWorkFactory
from alpha_defense.bootstrap import build_container
from alpha_defense.domain.incidents import CorrelationReason
from alpha_defense.transport.http.v1.schemas import ObservationInputSchema
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def test_s01_incident_and_pending_context_survive_restart(tmp_path: Path) -> None:
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
        idempotency_key="start-p10-session",
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

    created = first_container.analyze_contact.execute(
        actor=actor,
        source=source,
        observation_input=observation_input,
    )
    incident_id = created.incident.incident_id
    first_observation_id = created.observation.observation_id
    first_container.close()

    second_container = build_container(settings)
    restored = second_container.get_incident.execute(actor=actor, incident_id=incident_id)
    incident_uow = cast(IncidentUnitOfWorkFactory, second_container.unit_of_work)
    with incident_uow() as uow:
        restored_risk_state = uow.namespace_risk_states.get(actor.namespace_id)
    follow_up = second_container.analyze_contact.execute(
        actor=actor,
        source=source,
        observation_input=ObservationInput(
            source_event_id=f"{observation_input.source_event_id}-follow-up",
            occurred_at=observation_input.occurred_at + timedelta(seconds=1),
            payload=observation_input.payload,
        ),
    )
    second_container.close()

    assert restored.observation_ids == (first_observation_id,)
    assert restored.context_version == 1
    assert restored_risk_state is not None
    assert restored_risk_state.ingress_risk_epoch == 1
    assert restored_risk_state.analysis_pending
    assert follow_up.incident.incident_id == incident_id
    assert follow_up.incident.context_version == 2
    assert follow_up.risk_state.ingress_risk_epoch == 2
    assert follow_up.incident.timeline[-1].correlation_reason is CorrelationReason.CONVERSATION
