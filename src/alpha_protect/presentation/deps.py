"""Dependency providers for presentation layer."""

from __future__ import annotations

from functools import lru_cache

from alpha_protect.infrastructure.container import UseCaseRegistry, build_use_case_registry


@lru_cache
def _cached_use_case_registry() -> UseCaseRegistry:
    return build_use_case_registry()


def get_use_case_registry() -> UseCaseRegistry:
    return _cached_use_case_registry()
