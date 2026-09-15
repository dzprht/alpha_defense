"""Stable risk severity values."""

from enum import StrEnum


class Severity(StrEnum):
    """Risk label returned by domain policy."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
