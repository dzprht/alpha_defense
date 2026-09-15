"""Operational adapters that avoid raw private content."""

from alpha_defense.infrastructure.observability.audit import TransactionalAuditWriter

__all__ = ["TransactionalAuditWriter"]
