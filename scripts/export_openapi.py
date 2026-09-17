"""Export the backend OpenAPI document from implemented routes."""

from __future__ import annotations

import argparse
from pathlib import Path

from alpha_defense.bootstrap.openapi import export_openapi

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "contracts" / "http" / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    export_openapi(arguments.output)


if __name__ == "__main__":
    main()
