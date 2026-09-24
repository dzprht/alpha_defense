"""Run an isolated migrated backend for browser acceptance tests."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from alembic import command
from alembic.config import Config
from alpha_defense.bootstrap.app import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPOSITORY_ROOT / "apps" / "backend"


def main() -> None:
    with TemporaryDirectory(prefix="alpha-defense-browser-") as directory:
        runtime_root = Path(directory)
        database_path = runtime_root / "browser.db"
        media_root = runtime_root / "media"
        media_root.mkdir()
        database_url = f"sqlite:///{database_path}"

        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(config, "head")

        os.environ.update(
            APP_ENV="test",
            EXECUTION_MODE="mock",
            DATABASE_URL=database_url,
            SCHEMA_ROOT=str(REPOSITORY_ROOT / "contracts" / "fixtures"),
            CONTENT_ROOT=str(REPOSITORY_ROOT / "content"),
            FIXTURE_ROOT=str(REPOSITORY_ROOT / "fixtures"),
            MEDIA_ROOT=str(media_root),
            SESSION_SECRET=secrets.token_urlsafe(48),
            POLICY_VERSION="demo-risk-v1",
            TRUSTED_SUPPORT_CONTACT="900",
            CORS_ALLOW_ORIGINS="http://127.0.0.1:5173,http://localhost:5173",
            TRUSTED_HOSTS="127.0.0.1,localhost,testserver",
        )
        uvicorn.run(create_app(), host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
