#!/usr/bin/env python3
"""Refresh the local threat registry or show its current status."""

from __future__ import annotations

import argparse

from pydantic import ValidationError as PydanticValidationError

from alpha_defense.application.shared import ApplicationError
from alpha_defense.bootstrap import ConfigurationError, Settings, build_container


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("refresh", "status"),
        default="refresh",
        nargs="?",
        help="refresh is also the idempotent initial seed",
    )
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        container = build_container(Settings())
    except (ConfigurationError, PydanticValidationError):
        print("threat registry refresh failed: configuration_invalid")
        return 1
    try:
        if arguments.action == "status":
            status = container.threat_registry_status.execute()
            print(
                "threat registry: "
                f"status={status.availability.value}, "
                f"version={status.snapshot_version or '-'}, records={status.record_count}"
            )
            return 0
        result = container.refresh_threat_registry.execute()
        print(
            "threat registry refreshed: "
            f"version={result.snapshot_version}, records={result.record_count}, "
            f"published={str(result.published).lower()}"
        )
        return 0
    except ApplicationError as exc:
        print(f"threat registry refresh failed: {exc.code}")
        return 1
    finally:
        container.close()


if __name__ == "__main__":
    raise SystemExit(main())
