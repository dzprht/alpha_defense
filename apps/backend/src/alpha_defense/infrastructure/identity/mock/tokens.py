"""Opaque random pre-session tokens and deterministic HMAC-derived session tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping, Sequence

from alpha_defense.application.ports import JsonValue
from alpha_defense.domain.shared import EntityId
from alpha_defense.infrastructure.runtime import fingerprint_command, fingerprint_principal


class HmacSecurityTokens:
    def __init__(self, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("secret must contain at least 32 characters")
        self._secret = secret.encode("utf-8")

    def new_pre_session_token(self) -> str:
        return secrets.token_urlsafe(32)

    def fingerprint(self, token: str) -> str:
        if not token:
            raise ValueError("token must not be empty")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def fingerprint_principal(self, parts: Sequence[str]) -> str:
        return fingerprint_principal(parts)

    def fingerprint_command(self, command: Mapping[str, JsonValue]) -> str:
        return fingerprint_command(command)

    def derive_session_token(self, pre_session_token: str, session_id: EntityId) -> str:
        return self._derive(f"session:{pre_session_token}:{session_id}")

    def derive_csrf_token(self, bearer_token: str) -> str:
        return self._derive(f"csrf:{bearer_token}")

    def fingerprint_credentials(self, login: str, password: str) -> str:
        command = json.dumps([login, password], ensure_ascii=False, separators=(",", ":"))
        return hmac.new(self._secret, f"credentials:{command}".encode(), "sha256").hexdigest()

    def fingerprint_login(self, login: str) -> str:
        return hmac.new(self._secret, f"login:{login}".encode(), "sha256").hexdigest()

    def _derive(self, message: str) -> str:
        digest = hmac.digest(self._secret, message.encode("utf-8"), "sha256")
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
