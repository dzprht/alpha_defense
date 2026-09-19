#!/usr/bin/env python3
"""Validate the mandatory local catalogs without starting the HTTP service."""

from __future__ import annotations

import argparse
from pathlib import Path

from alpha_defense.infrastructure.content import CatalogValidationError, LocalCatalogLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema-root",
        type=Path,
        default=REPOSITORY_ROOT / "contracts" / "fixtures",
    )
    parser.add_argument("--content-root", type=Path, default=REPOSITORY_ROOT / "content")
    parser.add_argument("--fixture-root", type=Path, default=REPOSITORY_ROOT / "fixtures")
    parser.add_argument("--policy-version", default="demo-risk-v1")
    return parser


def main() -> int:
    args = _parser().parse_args()
    loader = LocalCatalogLoader(
        schema_root=args.schema_root,
        content_root=args.content_root,
        fixture_root=args.fixture_root,
        policy_version=args.policy_version,
    )
    try:
        snapshot = loader.load()
    except CatalogValidationError as exc:
        print(f"catalog invalid: {exc}")
        return 1
    print(
        "catalog valid: "
        f"policy={snapshot.policy.policy_version}, "
        f"fixtures={len(snapshot.fixtures)}, sha256={snapshot.catalog_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
