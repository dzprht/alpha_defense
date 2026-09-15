"""Canonical SHA-256 fingerprints for command replay and private principals."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping

from alpha_defense.application.ports.events import JsonValue


def fingerprint_command(command: Mapping[str, JsonValue]) -> str:
    """Hash a normalized JSON command independently of object key order."""

    if not isinstance(command, Mapping):
        raise TypeError("command must be a mapping")
    try:
        canonical = json.dumps(
            command,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("command must contain finite JSON values") from exc
    return hashlib.sha256(canonical).hexdigest()


def fingerprint_principal(parts: Iterable[str]) -> str:
    """Derive an opaque scope without persisting an actor token or composite identifier."""

    normalized: list[str] = []
    for part in parts:
        if not isinstance(part, str):
            raise TypeError("principal parts must be strings")
        if not part or part != part.strip():
            raise ValueError("principal parts must be non-empty and trimmed")
        normalized.append(part)
    if not normalized:
        raise ValueError("at least one principal part is required")
    material = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(material).hexdigest()
