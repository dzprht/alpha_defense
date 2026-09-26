"""Public schema, example, and deterministic OpenAPI checks."""

from __future__ import annotations

import json
from pathlib import Path

from alpha_defense.bootstrap.openapi import export_openapi
from alpha_defense.transport.http.v1.schemas import (
    AnonymousSessionResponse,
    ConsentResponse,
    EducationCardPageResponse,
    EducationCardResponse,
    LivenessResponse,
    ProblemDetails,
    ReadinessResponse,
    SessionResponse,
)

REPOSITORY_ROOT = Path(__file__).parents[4]


def test_committed_examples_match_public_schemas() -> None:
    examples = REPOSITORY_ROOT / "contracts" / "examples"

    live = LivenessResponse.model_validate_json(
        (examples / "health-live.v1.json").read_text(encoding="utf-8")
    )
    ready = ReadinessResponse.model_validate_json(
        (examples / "health-ready.v1.json").read_text(encoding="utf-8")
    )
    unavailable = ProblemDetails.model_validate_json(
        (examples / "health-ready-unavailable.v1.json").read_text(encoding="utf-8")
    )
    anonymous = AnonymousSessionResponse.model_validate_json(
        (examples / "session-anonymous.v1.json").read_text(encoding="utf-8")
    )
    active = SessionResponse.model_validate_json(
        (examples / "session-active.v1.json").read_text(encoding="utf-8")
    )
    consent = ConsentResponse.model_validate_json(
        (examples / "consent-granted.v1.json").read_text(encoding="utf-8")
    )
    education_page = EducationCardPageResponse.model_validate_json(
        (examples / "education-cards-page.v1.json").read_text(encoding="utf-8")
    )
    education_fallback = EducationCardResponse.model_validate_json(
        (examples / "education-card-fallback.v1.json").read_text(encoding="utf-8")
    )

    assert live.status == "alive"
    assert tuple(check.name for check in ready.checks) == ("database", "catalog")
    assert unavailable.status == 503
    assert unavailable.retryable
    assert anonymous.status == "anonymous"
    assert active.status == "active"
    assert consent.status.value == "granted"
    assert education_page.items[0].code == "credential_requests"
    assert education_fallback.fallback_reason == "unsupported_code"


def test_openapi_contains_only_implemented_endpoints_and_problem_media() -> None:
    contract = json.loads(
        (REPOSITORY_ROOT / "contracts" / "http" / "openapi.json").read_text(encoding="utf-8")
    )

    assert set(contract["paths"]) == {
        "/api/v1/accounts",
        "/api/v1/assessments/{assessment_id}",
        "/api/v1/assessments/{assessment_id}/guidance",
        "/api/v1/assessments/{assessment_id}/warning",
        "/api/v1/consents/{scope}",
        "/api/v1/education/cards",
        "/api/v1/education/cards/{code}",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/incidents/{incident_id}",
        "/api/v1/observations",
        "/api/v1/observations/{observation_id}",
        "/api/v1/observations/{observation_id}/reassess",
        "/api/v1/profile-templates",
        "/api/v1/profiles",
        "/api/v1/profiles/{profile_id}",
        "/api/v1/session",
        "/api/v1/sessions",
        "/api/v1/sessions/demo",
        "/api/v1/sessions/logout",
        "/api/v1/warnings/{warning_id}/present",
    }
    unavailable = contract["paths"]["/api/v1/health/ready"]["get"]["responses"]["503"]
    assert set(unavailable["content"]) == {"application/problem+json"}
    assert unavailable["content"]["application/problem+json"]["schema"] == (
        {"$ref": "#/components/schemas/ProblemDetails"}
    )
    for operation, status in (
        (contract["paths"]["/api/v1/sessions/demo"]["post"], "409"),
        (contract["paths"]["/api/v1/sessions"]["post"], "429"),
        (contract["paths"]["/api/v1/consents/{scope}"]["patch"], "403"),
    ):
        assert set(operation["responses"][status]["content"]) == {"application/problem+json"}


def test_openapi_export_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    export_openapi(first)
    export_openapi(second)

    assert first.read_bytes() == second.read_bytes()
    assert (
        first.read_bytes() == (REPOSITORY_ROOT / "contracts" / "http" / "openapi.json").read_bytes()
    )


def test_generated_web_types_cover_implemented_routes() -> None:
    generated = (
        REPOSITORY_ROOT / "apps" / "web" / "src" / "shared" / "api" / "generated" / "openapi.ts"
    ).read_text(encoding="utf-8")

    assert '"/api/v1/health/live"' in generated
    assert '"/api/v1/health/ready"' in generated
    assert '"/api/v1/session"' in generated
    assert '"/api/v1/sessions/demo"' in generated
    assert '"/api/v1/accounts"' in generated
    assert '"/api/v1/sessions"' in generated
    assert '"/api/v1/sessions/logout"' in generated
    assert '"/api/v1/consents/{scope}"' in generated
    assert '"/api/v1/education/cards"' in generated
    assert '"/api/v1/education/cards/{code}"' in generated
    assert '"/api/v1/assessments/{assessment_id}/warning"' in generated
    assert '"/api/v1/warnings/{warning_id}/present"' in generated
    assert '"/api/v1/observations"' in generated
    assert '"/api/v1/observations/{observation_id}/reassess"' in generated
    assert '"/api/v1/incidents/{incident_id}"' in generated
    assert '"/api/v1/assessments/{assessment_id}/guidance"' in generated
    assert '"/api/v1/profile-templates"' in generated
    assert '"/api/v1/profiles"' in generated
    assert '"/api/v1/profiles/{profile_id}"' in generated
