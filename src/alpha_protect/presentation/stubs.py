"""Helpers for standardized stub responses."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from alpha_protect.presentation.schemas import NotImplementedStubResponse


def build_not_implemented_response(detail: str) -> NotImplementedStubResponse:
    return NotImplementedStubResponse(
        request_id=uuid4(),
        detail=detail,
        timestamp=datetime.now(timezone.utc),
    )
