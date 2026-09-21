# ruff: noqa: RUF001
"""Offline trusted/lookalike domain checks for normalized web resources."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from alpha_defense.application.ports import ResourceAnalysisRequest
from alpha_defense.domain.detection import AnalysisResult, AnalysisStatus, AnalyzerKind, Signal
from alpha_defense.domain.shared import Provenance

URL_RULES_VERSION = "trusted-domain-rules-v1"

_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


class DeterministicUrlAnalyzer:
    """Compare a normalized host with the reviewed trusted-entity catalog."""

    def analyze(self, request: ResourceAnalysisRequest) -> AnalysisResult:
        host = urlsplit(request.normalized_url).hostname
        if host is None:
            raise ValueError("normalized_url must contain a host")
        trusted = any(
            host == domain or host.endswith(f".{domain}") for domain in request.trusted_domains
        )
        lookalike = not trusted and _contains_brand_marker(
            host,
            trusted_domains=request.trusted_domains,
            trusted_brands=request.trusted_brand_names,
        )
        signals = (
            (
                Signal(
                    code="lookalike_domain",
                    evidence_ref=request.evidence_ref,
                    strength=100,
                    source="trusted-domain-rules",
                ),
            )
            if lookalike
            else ()
        )
        return AnalysisResult(
            analyzer=AnalyzerKind.RESOURCE_URL,
            status=AnalysisStatus.OK,
            signals=signals,
            reason_codes=("trusted_domain" if trusted else "domain_rules_applied",),
            latency_ms=0,
            provenance=Provenance(
                execution_mode=request.execution_mode,
                provider="trusted-domain-rules",
                provider_version=URL_RULES_VERSION,
                data_version=request.trusted_catalog_version,
            ),
        )


def _contains_brand_marker(
    host: str,
    *,
    trusted_domains: tuple[str, ...],
    trusted_brands: tuple[str, ...],
) -> bool:
    compact_host = re.sub(r"[^a-z0-9]", "", host)
    markers: set[str] = set()
    for domain in trusted_domains:
        root = domain.split(".", maxsplit=1)[0]
        if len(root) >= 4:
            markers.add(root)
    for brand in trusted_brands:
        transliterated = brand.casefold().translate(_TRANSLITERATION)
        markers.update(
            token for token in re.findall(r"[a-z0-9]+", transliterated) if len(token) >= 4
        )
    generic = {"bank", "банк"}
    return any(marker not in generic and marker in compact_host for marker in markers)
