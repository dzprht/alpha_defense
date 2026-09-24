"""P15 persisted contact analysis, replay, freshness, and restart recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from alpha_defense.application.communications import ObservationInput
from alpha_defense.application.shared import StaleRevisionError
from alpha_defense.bootstrap import build_container
from alpha_defense.domain.communications import SmsPayload
from alpha_defense.domain.detection import AnalysisResult, AnalysisStatus, AnalyzerKind
from alpha_defense.domain.identity import ConsentScope, ConsentStatus
from alpha_defense.domain.shared import ExecutionMode, Provenance, Severity
from tests.catalog_helpers import REPOSITORY_ROOT, install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings


def _observation(
    source_event_id: str, text: str = "Назовите пароль от кабинета"
) -> ObservationInput:
    return ObservationInput(
        source_event_id=source_event_id,
        occurred_at=datetime(2026, 9, 24, 10, tzinfo=UTC),
        payload=SmsPayload(
            text=text,
            sender="+79991234567",
            conversation_id="conversation-p15",
        ),
    )


def _session(container: object) -> tuple[object, object]:
    bootstrap = container.identity_service.bootstrap_session(
        session_token=None, pre_session_token=None
    )
    assert bootstrap.pre_session_token is not None
    started = container.identity_service.start_session(
        pre_session_token=bootstrap.pre_session_token,
        idempotency_key="start-p15",
        profile_code="demo-user",
    )
    actor = container.identity_service.resolve_actor(started.session_token)
    container.identity_service.update_consent(
        actor=actor,
        idempotency_key="consent-p15",
        scope=ConsentScope.ANALYZE_COMMUNICATIONS,
        status=ConsentStatus.GRANTED,
        expected_revision=0,
    )
    return started.session_token, container.identity_service.resolve_actor(started.session_token)


def test_full_contact_persists_replays_and_restores_after_restart(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "contact.db"
    migrate(database_path)
    settings = make_settings(
        tmp_path,
        database_url=f"sqlite:///{database_path}",
        policy_version="demo-risk-v2",
        model_root=REPOSITORY_ROOT / "artifacts/text",
    )
    first = build_container(settings)
    token, actor = _session(first)
    result = first.complete_contact.submit(
        actor=actor,
        observation_input=_observation("message-1"),
        idempotency_key="submit-1",
    )
    repeated = first.complete_contact.submit(
        actor=actor,
        observation_input=_observation("message-1"),
        idempotency_key="submit-1",
    )
    assert repeated.assessment.assessment_id == result.assessment.assessment_id
    assert repeated.duplicate_source_event
    assert result.assessment.policy_version == "demo-risk-v2"
    assert result.assessment.severity in {Severity.HIGH, Severity.CRITICAL}
    assert result.incident.assessment_ids == (result.assessment.assessment_id,)
    assert not result.risk_state.analysis_pending
    assert result.warning is not None and result.warning.dispatched_at is not None
    with first.unit_of_work() as uow:
        assert len(uow.audit.list_all()) >= 4
        assert len(uow.outbox.list_all()) == 1
    first.close()

    second = build_container(settings)
    restored_actor = second.identity_service.resolve_actor(token)
    restored = second.complete_contact.get_assessment(
        actor=restored_actor, assessment_id=result.assessment.assessment_id
    )
    assert restored == result.assessment
    assert (
        second.get_incident.execute(
            actor=restored_actor, incident_id=result.incident.incident_id
        ).latest_assessment_id
        == restored.assessment_id
    )
    assert (
        second.complete_contact.get_guidance(
            actor=restored_actor, assessment_id=restored.assessment_id
        ).content_version
        == "demo-guidance-ru-v2"
    )
    reassessed = second.complete_contact.reassess(
        actor=restored_actor, observation_id=result.observation.observation_id
    )
    assert reassessed.assessment.assessment_id != restored.assessment_id
    assert reassessed.incident.assessment_ids == (
        restored.assessment_id,
        reassessed.assessment.assessment_id,
    )
    assert (
        second.complete_contact.get_assessment(
            actor=restored_actor, assessment_id=restored.assessment_id
        )
        == restored
    )
    second.close()


def test_new_evidence_during_inference_keeps_pending_and_rejects_stale_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "race.db"
    migrate(database_path)
    container = build_container(make_settings(tmp_path, database_url=f"sqlite:///{database_path}"))
    _, actor = _session(container)
    original_assess = container.assess_observation.execute
    inserted = False

    def concurrent_assess(**kwargs: object) -> object:
        nonlocal inserted
        if not inserted:
            inserted = True
            container.analyze_contact.execute(
                actor=actor,
                source="manual.web",
                observation_input=_observation("message-2", "Вторая просьба сообщить код"),
            )
        return original_assess(**kwargs)

    monkeypatch.setattr(container.assess_observation, "execute", concurrent_assess)
    with pytest.raises(StaleRevisionError):
        container.complete_contact.submit(
            actor=actor,
            observation_input=_observation("message-1"),
            idempotency_key="submit-race",
        )
    with container.unit_of_work() as uow:
        state = uow.namespace_risk_states.get(actor.namespace_id)
        assert state is not None and len(state.pending_analyses) == 2
        incident = uow.incidents.get_by_observation(state.pending_analyses[0].observation_id)
        assert incident is not None and incident.assessment_ids == ()
        assert uow.outbox.list_all() == ()
    monkeypatch.setattr(container.assess_observation, "execute", original_assess)
    recovered = container.complete_contact.submit(
        actor=actor,
        observation_input=_observation("message-1"),
        idempotency_key="submit-race",
    )
    assert recovered.incident.context_version == 2
    assert recovered.risk_state.analysis_pending
    assert len(recovered.risk_state.pending_observation_ids) == 1
    container.close()


def test_replay_after_new_evidence_does_not_create_another_assessment(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "late-replay.db"
    migrate(database_path)
    container = build_container(make_settings(tmp_path, database_url=f"sqlite:///{database_path}"))
    _, actor = _session(container)
    original = container.complete_contact.submit(
        actor=actor,
        observation_input=_observation("original"),
        idempotency_key="original-key",
    )
    container.analyze_contact.execute(
        actor=actor,
        source="manual.web",
        observation_input=_observation("new-evidence", "Вторая просьба сообщить код"),
    )
    replay = container.complete_contact.submit(
        actor=actor,
        observation_input=_observation("original"),
        idempotency_key="original-key",
    )
    assert replay.assessment.assessment_id == original.assessment.assessment_id
    assert replay.risk_state.analysis_pending
    assert replay.risk_state.pending_observation_ids != ()
    with container.unit_of_work() as uow:
        assert uow.assessments.list_for_observation(original.observation.observation_id) == (
            original.assessment,
        )
    container.close()


def test_warning_failure_rolls_back_assessment_and_keeps_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "rollback.db"
    migrate(database_path)
    container = build_container(make_settings(tmp_path, database_url=f"sqlite:///{database_path}"))
    _, actor = _session(container)

    def fail_warning(**_: object) -> None:
        raise RuntimeError("injected warning failure")

    original = container.warnings.create_in_unit_of_work
    monkeypatch.setattr(container.warnings, "create_in_unit_of_work", fail_warning)
    with pytest.raises(RuntimeError, match="injected warning failure"):
        container.complete_contact.submit(
            actor=actor,
            observation_input=_observation("rollback-message"),
            idempotency_key="rollback-key",
        )
    with container.unit_of_work() as uow:
        state = uow.namespace_risk_states.get(actor.namespace_id)
        assert state is not None and len(state.pending_analyses) == 1
        incident = uow.incidents.get_by_observation(state.pending_analyses[0].observation_id)
        assert incident is not None and incident.assessment_ids == ()
        assert uow.assessments.list_for_observation(state.pending_analyses[0].observation_id) == ()
        assert uow.outbox.list_all() == ()
    monkeypatch.setattr(container.warnings, "create_in_unit_of_work", original)
    recovered = container.complete_contact.submit(
        actor=actor,
        observation_input=_observation("rollback-message"),
        idempotency_key="rollback-key",
    )
    assert not recovered.risk_state.analysis_pending
    container.close()


def test_model_failure_is_saved_as_unknown_partial_not_low(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "model-failure.db"
    migrate(database_path)
    container = build_container(
        make_settings(
            tmp_path,
            database_url=f"sqlite:///{database_path}",
            policy_version="demo-risk-v2",
            model_root=REPOSITORY_ROOT / "artifacts/text",
        )
    )
    _, actor = _session(container)

    class UnavailableModel:
        def analyze(self, request: object) -> AnalysisResult:
            return AnalysisResult(
                analyzer=AnalyzerKind.TEXT_MODEL,
                status=AnalysisStatus.UNAVAILABLE,
                signals=(),
                reason_codes=("ml_model_failure",),
                latency_ms=0,
                provenance=Provenance(
                    ExecutionMode.MOCK, "trained-text-model", "failed", "unavailable"
                ),
            )

    container.assess_observation._text_model_analyzer = UnavailableModel()
    result = container.complete_contact.submit(
        actor=actor,
        observation_input=_observation("model-down", "Напоминаю о встрече завтра"),  # noqa: RUF001
        idempotency_key="model-down-key",
    )
    assert result.assessment.severity is Severity.UNKNOWN
    assert result.assessment.score is None
    assert result.assessment.completeness.value == "partial"
    assert result.warning is not None
    assert not result.risk_state.analysis_pending
    container.close()


def test_all_text_analyzers_unavailable_is_persisted_without_low_risk(tmp_path: Path) -> None:
    install_valid_catalog(tmp_path)
    database_path = tmp_path / "unavailable.db"
    migrate(database_path)
    container = build_container(
        make_settings(
            tmp_path,
            database_url=f"sqlite:///{database_path}",
            policy_version="demo-risk-v2",
            model_root=REPOSITORY_ROOT / "artifacts/text",
        )
    )
    _, actor = _session(container)

    class UnavailableAnalyzer:
        def __init__(self, kind: AnalyzerKind) -> None:
            self.kind = kind

        def analyze(self, request: object) -> AnalysisResult:
            return AnalysisResult(
                analyzer=self.kind,
                status=AnalysisStatus.UNAVAILABLE,
                signals=(),
                reason_codes=("analyzer_unavailable",),
                latency_ms=0,
                provenance=Provenance(ExecutionMode.MOCK, "test-analyzer", "failed", "unavailable"),
            )

    container.assess_observation._text_analyzer = UnavailableAnalyzer(AnalyzerKind.TEXT)
    container.assess_observation._text_model_analyzer = UnavailableAnalyzer(AnalyzerKind.TEXT_MODEL)
    result = container.complete_contact.submit(
        actor=actor,
        observation_input=_observation("all-analyzers-down", "Назовите пароль от кабинета"),
        idempotency_key="all-analyzers-down-key",
    )
    assert result.assessment.severity is Severity.UNKNOWN
    assert result.assessment.score is None
    assert result.assessment.completeness.value == "unavailable"
    assert result.warning is not None
    assert not result.risk_state.analysis_pending
    container.close()
