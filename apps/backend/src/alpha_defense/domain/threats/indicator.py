"""Typed and deterministic threat indicator normalization."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import SplitResult, urlsplit, urlunsplit

NORMALIZATION_VERSION = "indicator-v1"
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{1,254}$")


class IndicatorType(StrEnum):
    PHONE = "phone"
    DOMAIN = "domain"
    URL = "url"
    WALLET = "wallet"
    ACCOUNT_TOKEN = "account_token"
    IP = "ip"
    PATTERN_ID = "pattern_id"


@dataclass(frozen=True, slots=True)
class ThreatIndicator:
    indicator_type: IndicatorType
    normalized_value: str
    normalization_version: str = NORMALIZATION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.indicator_type, IndicatorType):
            raise TypeError("indicator_type must be an IndicatorType")
        if self.normalization_version != NORMALIZATION_VERSION:
            raise ValueError("normalization_version is not supported")
        if normalize_indicator(self.indicator_type, self.normalized_value) != self.normalized_value:
            raise ValueError("normalized_value is not canonical")

    @classmethod
    def from_raw(cls, indicator_type: IndicatorType, value: str) -> ThreatIndicator:
        return cls(
            indicator_type=indicator_type,
            normalized_value=normalize_indicator(indicator_type, value),
        )


def normalize_indicator(indicator_type: IndicatorType, value: str) -> str:
    if not isinstance(indicator_type, IndicatorType):
        raise TypeError("indicator_type must be an IndicatorType")
    if not isinstance(value, str):
        raise TypeError("indicator value must be a string")
    trimmed = value.strip()
    if not trimmed or len(trimmed) > 2048:
        raise ValueError("indicator value must contain 1..2048 characters")
    if indicator_type is IndicatorType.DOMAIN:
        return _normalize_domain(trimmed)
    if indicator_type is IndicatorType.URL:
        return _normalize_url(trimmed)
    if indicator_type is IndicatorType.PHONE:
        return _normalize_phone(trimmed)
    if indicator_type is IndicatorType.IP:
        return ipaddress.ip_address(trimmed).compressed
    if not _TOKEN.fullmatch(trimmed):
        raise ValueError("opaque indicator must use the stable token format")
    if indicator_type is IndicatorType.PATTERN_ID:
        return trimmed.lower()
    return trimmed


def _normalize_domain(value: str) -> str:
    domain = value.rstrip(".")
    try:
        ascii_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("domain is not valid IDNA") from exc
    if len(ascii_domain) > 253:
        raise ValueError("domain is too long")
    labels = ascii_domain.split(".")
    if len(labels) < 2 or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        raise ValueError("domain must contain valid DNS labels")
    return ascii_domain


def _normalize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL authority is invalid") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("URL must use http or https and contain a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL user information is not supported")
    host = _normalize_url_host(parsed.hostname)
    if ":" in host:
        host = f"[{host}]"
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    normalized = SplitResult(
        scheme=scheme,
        netloc=host,
        path=parsed.path or "/",
        query=parsed.query,
        fragment="",
    )
    return urlunsplit(normalized)


def _normalize_url_host(value: str) -> str:
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        return _normalize_domain(value)


def _normalize_phone(value: str) -> str:
    compact = re.sub(r"[\s()-]", "", value)
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", compact):
        raise ValueError("phone must be an E.164 number")
    return compact
