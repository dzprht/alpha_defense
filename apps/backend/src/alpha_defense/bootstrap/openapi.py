"""Deterministic OpenAPI export for the routes that actually exist."""

from __future__ import annotations

import json
from pathlib import Path

from alpha_defense.application.ports import ReadinessCheck, ReadinessReport
from alpha_defense.bootstrap.app import create_http_app


class _ContractReadiness:
    def check(self) -> ReadinessReport:
        return ReadinessReport((ReadinessCheck("contract", True, "ready"),))


def export_openapi(output_path: Path) -> None:
    """Write canonical UTF-8 JSON, replacing output only when bytes differ."""

    app = create_http_app(readiness=_ContractReadiness())
    contract = app.openapi()
    ready_responses = contract["paths"]["/api/v1/health/ready"]["get"]["responses"]
    unavailable_content = ready_responses["503"]["content"]
    json_schema = unavailable_content["application/json"]["schema"]
    unavailable_content["application/problem+json"]["schema"] = json_schema
    unavailable_content.pop("application/json")
    payload = (
        json.dumps(
            contract,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.is_file() and output_path.read_text(encoding="utf-8") == payload:
        return
    output_path.write_text(payload, encoding="utf-8", newline="\n")
