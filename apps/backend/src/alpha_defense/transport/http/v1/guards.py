"""Prepared HTTP command guards shared by future mutating routes."""

from __future__ import annotations

import hmac

from fastapi import Request

from alpha_defense.transport.http.v1.dependencies import CSRF_COOKIE_NAME
from alpha_defense.transport.http.v1.errors import RequestGuardError

CSRF_HEADER_NAME = "X-CSRF-Token"
IDEMPOTENCY_HEADER_NAME = "Idempotency-Key"


def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    header = request.headers.get(CSRF_HEADER_NAME)
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise RequestGuardError(
            status=403,
            code="csrf_failed",
            detail="Проверка защиты команды не пройдена.",
        )


def require_idempotency_key(request: Request) -> str:
    key = request.headers.get(IDEMPOTENCY_HEADER_NAME)
    if key is None or not key or key != key.strip() or len(key) > 255 or not key.isprintable():
        raise RequestGuardError(
            status=400,
            code="idempotency_key_required",
            detail="Для команды нужен корректный Idempotency-Key.",
        )
    return key
