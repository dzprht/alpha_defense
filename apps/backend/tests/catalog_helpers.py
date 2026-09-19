"""Helpers for installing the committed synthetic catalog into isolated test roots."""

from __future__ import annotations

import shutil
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def install_valid_catalog(tmp_path: Path) -> None:
    """Copy immutable repository inputs so a test can safely corrupt its own copy."""

    shutil.copytree(
        REPOSITORY_ROOT / "contracts" / "fixtures",
        tmp_path / "schemas",
        dirs_exist_ok=True,
    )
    shutil.copytree(REPOSITORY_ROOT / "content", tmp_path / "content", dirs_exist_ok=True)
    shutil.copytree(REPOSITORY_ROOT / "fixtures", tmp_path / "fixtures", dirs_exist_ok=True)
