"""Versioned normalization of communication indicators without I/O."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import SplitResult, urlsplit, urlunsplit

NORMALIZATION_VERSION = "communication-v1"
MAX_INDICATORS = 50

_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_URL_CANDIDATE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,!?;:)]}\u00bb\u201d\u2019"


class CommunicationIndicatorType(StrEnum):
    PHONE = "phone"
    URL = "url"
    DOMAIN = "domain"


class NormalizationStatus(StrEnum):
    NORMALIZED = "normalized"
    INVALID = "invalid"


class IndicatorOrigin(StrEnum):
    SENDER = "sender"
    CALLER = "caller"
    EMBEDDED_TEXT = "embedded_text"
    RESOURCE_URL = "resource_url"
    RESOURCE_DOMAIN = "resource_domain"


@dataclass(frozen=True, slots=True)
class NormalizedIndicator:
    indicator_type: CommunicationIndicatorType
    origin: IndicatorOrigin
    raw_value: str
    normalized_value: str | None
    status: NormalizationStatus
    normalization_version: str = NORMALIZATION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.indicator_type, CommunicationIndicatorType):
            raise TypeError("indicator_type must be a CommunicationIndicatorType")
        if not isinstance(self.origin, IndicatorOrigin):
            raise TypeError("origin must be an IndicatorOrigin")
        if not isinstance(self.raw_value, str) or not self.raw_value or len(self.raw_value) > 2048:
            raise ValueError("raw_value must contain 1..2048 characters")
        if not isinstance(self.status, NormalizationStatus):
            raise TypeError("status must be a NormalizationStatus")
        if self.normalization_version != NORMALIZATION_VERSION:
            raise ValueError("normalization_version is not supported")
        if self.status is NormalizationStatus.INVALID:
            if self.normalized_value is not None:
                raise ValueError("invalid indicators cannot have a normalized value")
            return
        if not isinstance(self.normalized_value, str):
            raise ValueError("normalized indicators require a normalized value")
        canonical = normalize_value(self.indicator_type, self.normalized_value)
        if canonical != self.normalized_value:
            raise ValueError("normalized_value is not canonical")


def normalize_value(indicator_type: CommunicationIndicatorType, value: str) -> str:
    if not isinstance(indicator_type, CommunicationIndicatorType):
        raise TypeError("indicator_type must be a CommunicationIndicatorType")
    if not isinstance(value, str):
        raise TypeError("indicator value must be a string")
    if not value or len(value) > 2048:
        raise ValueError("indicator value must contain 1..2048 characters")
    if indicator_type is CommunicationIndicatorType.PHONE:
        return _normalize_phone(value)
    if indicator_type is CommunicationIndicatorType.URL:
        return _normalize_url(value)
    return _normalize_domain(value)


def normalize_candidate(
    indicator_type: CommunicationIndicatorType,
    value: str,
    *,
    origin: IndicatorOrigin,
) -> NormalizedIndicator:
    try:
        normalized = normalize_value(indicator_type, value)
    except (TypeError, ValueError):
        return NormalizedIndicator(
            indicator_type=indicator_type,
            origin=origin,
            raw_value=value,
            normalized_value=None,
            status=NormalizationStatus.INVALID,
        )
    return NormalizedIndicator(
        indicator_type=indicator_type,
        origin=origin,
        raw_value=value,
        normalized_value=normalized,
        status=NormalizationStatus.NORMALIZED,
    )


def indicators_from_text(
    text: str,
    *,
    sender: str | None = None,
    sender_origin: IndicatorOrigin = IndicatorOrigin.SENDER,
) -> tuple[NormalizedIndicator, ...]:
    indicators: list[NormalizedIndicator] = []
    if sender is not None:
        indicators.append(
            normalize_candidate(
                CommunicationIndicatorType.PHONE,
                sender,
                origin=sender_origin,
            )
        )
    for match in _URL_CANDIDATE.finditer(text):
        raw_url = match.group(0).rstrip(_TRAILING_URL_PUNCTUATION)
        if not raw_url:
            continue
        url = normalize_candidate(
            CommunicationIndicatorType.URL,
            raw_url,
            origin=IndicatorOrigin.EMBEDDED_TEXT,
        )
        indicators.append(url)
        if url.normalized_value is not None:
            domain = _domain_from_url(
                raw_url,
                url.normalized_value,
                origin=IndicatorOrigin.EMBEDDED_TEXT,
            )
            if domain is not None:
                indicators.append(domain)
    if len(indicators) > MAX_INDICATORS:
        raise ValueError(f"observation has more than {MAX_INDICATORS} indicators")
    return _deduplicate(indicators)


def indicators_from_resource(url: str) -> tuple[NormalizedIndicator, ...]:
    normalized_url = normalize_candidate(
        CommunicationIndicatorType.URL,
        url,
        origin=IndicatorOrigin.RESOURCE_URL,
    )
    if normalized_url.status is NormalizationStatus.INVALID:
        return (normalized_url,)
    assert normalized_url.normalized_value is not None
    domain = _domain_from_url(
        url,
        normalized_url.normalized_value,
        origin=IndicatorOrigin.RESOURCE_DOMAIN,
    )
    return (normalized_url,) if domain is None else (normalized_url, domain)


def _domain_from_url(
    raw_url: str,
    normalized_url: str,
    *,
    origin: IndicatorOrigin,
) -> NormalizedIndicator | None:
    normalized_domain = urlsplit(normalized_url).hostname
    assert normalized_domain is not None
    try:
        ipaddress.ip_address(normalized_domain)
    except ValueError:
        raw_domain = urlsplit(raw_url).hostname or raw_url
        return NormalizedIndicator(
            indicator_type=CommunicationIndicatorType.DOMAIN,
            origin=origin,
            raw_value=raw_domain,
            normalized_value=normalized_domain,
            status=NormalizationStatus.NORMALIZED,
        )
    return None


def _deduplicate(indicators: list[NormalizedIndicator]) -> tuple[NormalizedIndicator, ...]:
    unique: list[NormalizedIndicator] = []
    seen: set[tuple[object, ...]] = set()
    for indicator in indicators:
        key = (
            indicator.indicator_type,
            indicator.origin,
            indicator.raw_value,
            indicator.normalized_value,
            indicator.status,
        )
        if key not in seen:
            seen.add(key)
            unique.append(indicator)
    if len(unique) > MAX_INDICATORS:
        raise ValueError(f"observation has more than {MAX_INDICATORS} indicators")
    return tuple(unique)


def _normalize_phone(value: str) -> str:
    compact = re.sub(r"[\s()-]", "", value)
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", compact):
        raise ValueError("phone must be an E.164 number")
    return compact


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
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError("URL cannot contain whitespace or control characters")
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
    return urlunsplit(
        SplitResult(
            scheme=scheme,
            netloc=host,
            path=parsed.path or "/",
            query=parsed.query,
            fragment="",
        )
    )


def _normalize_url_host(value: str) -> str:
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        return _normalize_domain(value)
