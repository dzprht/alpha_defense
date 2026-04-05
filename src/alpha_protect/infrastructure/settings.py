"""Application settings loaded from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(slots=True, frozen=True)
class Settings:
    app_name: str
    api_prefix: str
    log_level: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "Alpha Protect API"),
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
