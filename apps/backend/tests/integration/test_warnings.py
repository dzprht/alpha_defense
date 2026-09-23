"""P13 warning lifecycle across in-memory and SQLite adapters."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from alpha_defense.application.education import AllowedActionView, GetGuidance
from alpha_defense.application.protection import WarningService
from alpha_defense.application.shared import (
    ActorContext,
    ActorRole,
    ResourceNotFoundError,
    ValidationError,
)
from alpha_defense.application.workflows import PublishWarning
from alpha_defense.bootstrap import build_container
from alpha_defense.domain.detection import (
    AssessmentCompleteness,
    AssessmentTargetKind,
    RiskAssessment,
)
from alpha_defense.domain.protection import WarningResponse
from alpha_defense.domain.shared import EntityId, ExecutionMode, Provenance, Severity
from alpha_defense.infrastructure.content import LocalCatalogLoader
from alpha_defense.infrastructure.persistence.in_memory import InMemoryUnitOfWorkFactory
from alpha_defense.infrastructure.runtime import SystemClock, UuidGenerator
from tests.catalog_helpers import install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def _id(number: int) -> EntityId:
    return EntityId(UUID(int=number))


@pytest.fixture(params=["memory", "sqlite"])
def warning_context(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Iterator[tuple[PublishWarning, WarningService, ActorContext]]:
    install_valid_catalog(tmp_path)
    catalog = LocalCatalogLoader(
        schema_root=tmp_path / "schemas",
        content_root=tmp_path / "content",
        fixture_root=tmp_path / "fixtures",
        policy_version="demo-risk-v1",
    )
    if request.param == "memory":
        service = WarningService(
            unit_of_work=InMemoryUnitOfWorkFactory(),
            clock=SystemClock(),
            id_generator=UuidGenerator(),
        )
        actor = ActorContext(
            user_id=_id(1),
            session_id=_id(2),
            namespace_id=_id(3),
            roles=frozenset({ActorRole.DEMO_USER}),
            consent_revision=0,
            execution_mode=ExecutionMode.MOCK,
        )
        yield PublishWarning(guidance=GetGuidance(catalog), warnings=service), service, actor
        return

    database_path = tmp_path / "warning.db"
    migrate(database_path)
    container = build_container(make_settings(tmp_path, database_url=f"sqlite:///{database_path}"))
    bootstrap = container.identity_service.bootstrap_session(
        session_token=None, pre_session_token=None
    )
    assert bootstrap.pre_session_token is not None
    started = container.identity_service.start_session(
        pre_session_token=bootstrap.pre_session_token,
        idempotency_key="start-warning-session",
        profile_code="demo-user",
    )
    actor = container.identity_service.resolve_actor(started.session_token)
    yield container.publish_warning, container.warnings, actor
    container.close()


def _assessment(actor: ActorContext, *, severity: Severity = Severity.HIGH) -> RiskAssessment:
    return RiskAssessment(
        assessment_id=_id(400),
        owner_id=actor.user_id,
        session_id=actor.session_id,
        namespace_id=actor.namespace_id,
        target_kind=AssessmentTargetKind.OBSERVATION,
        target_id=_id(500),
        severity=severity,
        score=70 if severity is Severity.HIGH else 5,
        score_kind="heuristic",
        completeness=AssessmentCompleteness.COMPLETE,
        signals=(),
        applied_modifiers=(),
        reason_codes=("credential_request",) if severity is Severity.HIGH else (),
        analyzer_results=(),
        policy_version="demo-risk-v1",
        analysis_plan_version="observation-v1",
        assessed_at=datetime(2026, 9, 24, 10, tzinfo=UTC),
        context_version=1,
        provenance=Provenance(ExecutionMode.MOCK, "fixture", "1", "1"),
        has_mock_evidence=True,
    )


def _actions() -> tuple[AllowedActionView, ...]:
    return (
        AllowedActionView(
            code="cancel_transfer",
            enabled=True,
            disabled_reason=None,
            requires_confirmation=False,
            target_id=_id(600),
            target_revision=2,
        ),
        AllowedActionView(
            code="execute_transfer",
            enabled=False,
            disabled_reason="Высокий риск.",
            requires_confirmation=True,
            target_id=_id(600),
            target_revision=2,
        ),
    )


def test_warning_delivery_render_response_are_distinct_and_repeated_safely(
    warning_context: tuple[PublishWarning, WarningService, ActorContext],
) -> None:
    publisher, service, actor = warning_context
    assessment = _assessment(actor)
    created = publisher.execute(actor=actor, assessment=assessment, allowed_actions=_actions())
    assert created is not None
    repeated = publisher.execute(actor=actor, assessment=assessment, allowed_actions=_actions())
    assert repeated == created
    assert service.list_dispatched(actor=actor) == ()
    with pytest.raises(ValidationError):
        service.present(actor=actor, warning_id=created.warning_id)

    dispatched = service.dispatch(actor=actor, warning_id=created.warning_id)
    assert dispatched.dispatched_at is not None
    assert dispatched.presented_at is None
    assert service.list_dispatched(actor=actor) == (dispatched,)
    assert service.dispatch(actor=actor, warning_id=created.warning_id) == dispatched
    with pytest.raises(ValidationError):
        service.respond(
            actor=actor, warning_id=created.warning_id, response=WarningResponse.DISMISSED
        )

    presented = service.present(actor=actor, warning_id=created.warning_id)
    assert presented.presented_at is not None
    assert presented.responded_at is None
    assert service.present(actor=actor, warning_id=created.warning_id) == presented
    dismissed = service.respond(
        actor=actor, warning_id=created.warning_id, response=WarningResponse.DISMISSED
    )
    assert dismissed.response is WarningResponse.DISMISSED
    assert dismissed.allowed_actions == created.allowed_actions
    assert dismissed.revision == 3
    assert (
        service.respond(
            actor=actor, warning_id=created.warning_id, response=WarningResponse.DISMISSED
        )
        == dismissed
    )
    with pytest.raises(ValidationError):
        service.respond(
            actor=actor, warning_id=created.warning_id, response=WarningResponse.ACKNOWLEDGED
        )


def test_warning_rejects_other_scope_and_disabled_action(
    warning_context: tuple[PublishWarning, WarningService, ActorContext],
) -> None:
    publisher, service, actor = warning_context
    assessment = _assessment(actor)
    created = publisher.execute(actor=actor, assessment=assessment, allowed_actions=_actions())
    assert created is not None
    foreign = ActorContext(
        user_id=_id(999),
        session_id=actor.session_id,
        namespace_id=actor.namespace_id,
        roles=actor.roles,
        consent_revision=actor.consent_revision,
        execution_mode=actor.execution_mode,
    )
    with pytest.raises(ResourceNotFoundError):
        service.get(actor=foreign, warning_id=created.warning_id)
    with pytest.raises(ResourceNotFoundError):
        service.dispatch(actor=foreign, warning_id=created.warning_id)
    assert service.list_dispatched(actor=foreign) == ()
    with pytest.raises(ResourceNotFoundError):
        publisher.execute(actor=foreign, assessment=assessment, allowed_actions=_actions())
    with pytest.raises(ResourceNotFoundError):
        service.get(actor=replace(actor, namespace_id=_id(998)), warning_id=created.warning_id)

    service.dispatch(actor=actor, warning_id=created.warning_id)
    service.present(actor=actor, warning_id=created.warning_id)
    with pytest.raises(ValidationError):
        service.respond(
            actor=actor,
            warning_id=created.warning_id,
            response=WarningResponse.ACTION_SELECTED,
            selected_action_code="execute_transfer",
        )
    selected = service.respond(
        actor=actor,
        warning_id=created.warning_id,
        response=WarningResponse.ACTION_SELECTED,
        selected_action_code="cancel_transfer",
    )
    assert selected.selected_action_code == "cancel_transfer"
    assert selected.allowed_actions[1].enabled is False


def test_low_complete_assessment_creates_no_warning(
    warning_context: tuple[PublishWarning, WarningService, ActorContext],
) -> None:
    publisher, service, actor = warning_context
    assessment = _assessment(actor, severity=Severity.LOW)
    assert publisher.execute(actor=actor, assessment=assessment, allowed_actions=_actions()) is None
    assert service.list_dispatched(actor=actor) == ()


def test_unavailable_assessment_still_produces_explicit_warning(
    warning_context: tuple[PublishWarning, WarningService, ActorContext],
) -> None:
    publisher, _, actor = warning_context
    unavailable = replace(
        _assessment(actor),
        severity=Severity.UNKNOWN,
        score=None,
        completeness=AssessmentCompleteness.UNAVAILABLE,
        reason_codes=(),
    )
    warning = publisher.execute(actor=actor, assessment=unavailable, allowed_actions=_actions())
    assert warning is not None
    assert warning.severity is Severity.UNKNOWN
    assert "не" in warning.explanation.lower()


def test_warning_creation_rolls_back_with_its_audit(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    catalog = LocalCatalogLoader(
        schema_root=tmp_path / "schemas",
        content_root=tmp_path / "content",
        fixture_root=tmp_path / "fixtures",
        policy_version="demo-risk-v1",
    )
    factory = InMemoryUnitOfWorkFactory()
    service = WarningService(
        unit_of_work=factory, clock=SystemClock(), id_generator=UuidGenerator()
    )
    publisher = PublishWarning(guidance=GetGuidance(catalog), warnings=service)
    actor = ActorContext(
        user_id=_id(1),
        session_id=_id(2),
        namespace_id=_id(3),
        roles=frozenset({ActorRole.DEMO_USER}),
        consent_revision=0,
        execution_mode=ExecutionMode.MOCK,
    )
    with factory() as uow:
        warning = publisher.execute_in_unit_of_work(
            uow=uow, actor=actor, assessment=_assessment(actor), allowed_actions=_actions()
        )
        assert warning is not None
        assert len(uow.audit.list_all()) == 1
    assert warning is not None
    with pytest.raises(ResourceNotFoundError):
        service.get(actor=actor, warning_id=warning.warning_id)
    with factory() as uow:
        assert uow.audit.list_all() == ()


def test_sqlite_warning_and_actual_presentation_survive_restart(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "restart-warning.db"
    migrate(database_path)
    settings = make_settings(tmp_path, database_url=f"sqlite:///{database_path}")
    first = build_container(settings)
    bootstrap = first.identity_service.bootstrap_session(session_token=None, pre_session_token=None)
    assert bootstrap.pre_session_token is not None
    started = first.identity_service.start_session(
        pre_session_token=bootstrap.pre_session_token,
        idempotency_key="restart-warning-session",
        profile_code="demo-user",
    )
    actor = first.identity_service.resolve_actor(started.session_token)
    warning = first.publish_warning.execute(
        actor=actor, assessment=_assessment(actor), allowed_actions=_actions()
    )
    assert warning is not None
    first.warnings.dispatch(actor=actor, warning_id=warning.warning_id)
    first.close()

    second = build_container(settings)
    restored = second.warnings.get(actor=actor, warning_id=warning.warning_id)
    assert restored.dispatched_at is not None
    assert restored.presented_at is None
    assert restored.allowed_actions == warning.allowed_actions
    presented = second.warnings.present(actor=actor, warning_id=warning.warning_id)
    assert presented.presented_at is not None
    second.close()
