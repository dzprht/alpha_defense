"""Public schema, example, and deterministic OpenAPI checks."""

from __future__ import annotations

import json
from pathlib import Path

from alpha_defense.bootstrap.openapi import export_openapi
from alpha_defense.transport.http.v1.schemas import (
    AnonymousSessionResponse,
    ConsentResponse,
    LivenessResponse,
    ProblemDetails,
    SessionResponse,
)

REPOSITORY_ROOT = Path(__file__).parents[4]


def test_committed_examples_match_public_schemas() -> None:
    examples = REPOSITORY_ROOT / "contracts" / "examples"

    live = LivenessResponse.model_validate_json(
        (examples / "health-live.v1.json").read_text(encoding="utf-8")
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

    assert live.status == "alive"
    assert unavailable.status == 503
    assert unavailable.retryable
    assert anonymous.status == "anonymous"
    assert active.status == "active"
    assert consent.status.value == "granted"


def test_openapi_contains_only_implemented_endpoints_and_problem_media() -> None:
    contract = json.loads(
        (REPOSITORY_ROOT / "contracts" / "http" / "openapi.json").read_text(encoding="utf-8")
    )

    assert set(contract["paths"]) == {
        "/api/v1/consents/{scope}",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/session",
        "/api/v1/sessions/demo",
    }
    unavailable = contract["paths"]["/api/v1/health/ready"]["get"]["responses"]["503"]
    assert set(unavailable["content"]) == {"application/problem+json"}
    assert unavailable["content"]["application/problem+json"]["schema"] == (
        {"$ref": "#/components/schemas/ProblemDetails"}
    )
    for operation, status in (
        (contract["paths"]["/api/v1/sessions/demo"]["post"], "409"),
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
    assert '"/api/v1/consents/{scope}"' in generated
