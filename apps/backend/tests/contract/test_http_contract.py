"""Public schema, example, and deterministic OpenAPI checks."""

from __future__ import annotations

import json
from pathlib import Path

from alpha_defense.bootstrap.openapi import export_openapi
from alpha_defense.transport.http.v1.schemas import LivenessResponse, ProblemDetails

REPOSITORY_ROOT = Path(__file__).parents[4]


def test_committed_examples_match_public_schemas() -> None:
    examples = REPOSITORY_ROOT / "contracts" / "examples"

    live = LivenessResponse.model_validate_json(
        (examples / "health-live.v1.json").read_text(encoding="utf-8")
    )
    unavailable = ProblemDetails.model_validate_json(
        (examples / "health-ready-unavailable.v1.json").read_text(encoding="utf-8")
    )

    assert live.status == "alive"
    assert unavailable.status == 503
    assert unavailable.retryable


def test_openapi_contains_only_implemented_endpoints_and_problem_media() -> None:
    contract = json.loads(
        (REPOSITORY_ROOT / "contracts" / "http" / "openapi.json").read_text(encoding="utf-8")
    )

    assert set(contract["paths"]) == {
        "/api/v1/health/live",
        "/api/v1/health/ready",
    }
    unavailable = contract["paths"]["/api/v1/health/ready"]["get"]["responses"]["503"]
    assert set(unavailable["content"]) == {"application/problem+json"}
    assert unavailable["content"]["application/problem+json"]["schema"] == (
        {"$ref": "#/components/schemas/ProblemDetails"}
    )


def test_openapi_export_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    export_openapi(first)
    export_openapi(second)

    assert first.read_bytes() == second.read_bytes()
    assert (
        first.read_bytes() == (REPOSITORY_ROOT / "contracts" / "http" / "openapi.json").read_bytes()
    )


def test_generated_web_types_cover_health_routes() -> None:
    generated = (
        REPOSITORY_ROOT / "apps" / "web" / "src" / "shared" / "api" / "generated" / "openapi.ts"
    ).read_text(encoding="utf-8")

    assert '"/api/v1/health/live"' in generated
    assert '"/api/v1/health/ready"' in generated
