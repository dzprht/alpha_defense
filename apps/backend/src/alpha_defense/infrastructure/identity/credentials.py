"""Argon2id password hashing behind the identity credential port."""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2Credentials:
    def __init__(self) -> None:
        self._hasher = PasswordHasher(type=Type.ID)
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, password_hash: str | None, password: str) -> bool:
        selected_hash = self._dummy_hash if password_hash is None else password_hash
        try:
            return self._hasher.verify(selected_hash, password)
        except (InvalidHashError, VerificationError):
            return False
