"""Composition root for the Alpha Defense backend."""

from alpha_defense.bootstrap.app import create_app, create_http_app
from alpha_defense.bootstrap.container import ConfigurationError, Container, build_container
from alpha_defense.bootstrap.settings import AppEnvironment, Settings

__all__ = [
    "AppEnvironment",
    "ConfigurationError",
    "Container",
    "Settings",
    "build_container",
    "create_app",
    "create_http_app",
]
