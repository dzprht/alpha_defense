"""Bootstrap composition of the trained model and rule-based assessment."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from alpha_defense.application.detection import ObservationAnalysisInput
from alpha_defense.application.shared import ActorContext, ActorRole
from alpha_defense.bootstrap import ConfigurationError, build_container
from alpha_defense.domain.communications import ObservationKind
from alpha_defense.domain.detection import AnalysisStatus, AnalyzerKind, AssessmentCompleteness
from alpha_defense.domain.shared import EntityId, ExecutionMode
from tests.catalog_helpers import REPOSITORY_ROOT, install_valid_catalog
from tests.contract.test_uow_contract import migrate
from tests.unit.test_settings import make_settings

MODEL_ROOT = REPOSITORY_ROOT / "artifacts/text"


def _id(value: int) -> EntityId:
    return EntityId(UUID(int=value))


def test_bootstrap_model_rules_policy_and_guidance_form_one_internal_assessment(
    tmp_path: Path,
) -> None:
    install_valid_catalog(tmp_path)
    migrate(tmp_path / "app.db")
    container = build_container(
        make_settings(tmp_path, policy_version="demo-risk-v2", model_root=MODEL_ROOT)
    )
    actor = ActorContext(
        user_id=_id(1),
        session_id=_id(2),
        namespace_id=_id(3),
        roles=frozenset({ActorRole.DEMO_USER}),
        consent_revision=0,
        execution_mode=ExecutionMode.MOCK,
    )
    assessment = container.assess_observation.execute(
        actor=actor,
        observation=ObservationAnalysisInput(
            observation_id=_id(10),
            owner_id=actor.user_id,
            session_id=actor.session_id,
            namespace_id=actor.namespace_id,
            kind=ObservationKind.SMS,
            text="Сообщите код подтверждения для перевода",
            raw_resource_url=None,
            normalized_resource_url=None,
            normalized_indicators=(),
            media_refs=(),
            context_version=1,
            execution_mode=ExecutionMode.MOCK,
        ),
    )
    guidance = container.get_guidance.execute(
        actor=actor, assessment=assessment, allowed_actions=()
    )
    container.close()

    assert assessment.policy_version == "demo-risk-v2"
    assert assessment.analysis_plan_version == "observation-analysis-v2"
    assert assessment.completeness is AssessmentCompleteness.COMPLETE
    results = {item.analyzer: item for item in assessment.analyzer_results}
    assert set(results) == set(AnalyzerKind)
    assert results[AnalyzerKind.TEXT].status is AnalysisStatus.OK
    assert results[AnalyzerKind.TEXT_MODEL].status is AnalysisStatus.OK
    assert results[AnalyzerKind.TEXT].model_score is None
    assert results[AnalyzerKind.TEXT_MODEL].model_score is not None
    assert results[AnalyzerKind.TEXT_MODEL].provenance.provider_version == "text-tfidf-logreg-v1"
    assert guidance.content_version == "demo-guidance-ru-v2"
    assert guidance.unmapped_reason_codes == ()


def test_model_enabled_bootstrap_rejects_missing_or_tampered_artifact(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, policy_version="demo-risk-v2")
    with pytest.raises(ConfigurationError, match="MODEL_ROOT is required"):
        build_container(settings)

    model_root = tmp_path / "model"
    model_root.mkdir()
    (model_root / "model.v1.json").write_bytes((MODEL_ROOT / "model.v1.json").read_bytes())
    (model_root / "model.v1.joblib").write_bytes(
        (MODEL_ROOT / "model.v1.joblib").read_bytes() + b"x"
    )
    with pytest.raises(ConfigurationError, match="no valid trusted text model"):
        build_container(
            make_settings(tmp_path, policy_version="demo-risk-v2", model_root=model_root)
        )
