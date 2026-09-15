"""Executable checks for the clean-architecture import direction."""

from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).parents[2] / "src"

_ALLOWED_INTERNAL_LAYERS = {
    "domain": frozenset({"domain"}),
    "application": frozenset({"application", "domain"}),
    "infrastructure": frozenset({"infrastructure", "application", "domain"}),
    "transport": frozenset({"transport", "application"}),
    "bootstrap": frozenset({"bootstrap", "transport", "infrastructure", "application", "domain"}),
}
_STDLIB_ROOTS = frozenset(sys.stdlib_module_names) | {"__future__"}


@dataclass(frozen=True, slots=True, order=True)
class ImportViolation:
    path: Path
    line: int
    imported_module: str
    reason: str


def _module_name(path: Path, source_root: Path) -> str:
    parts = list(path.relative_to(source_root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_name(path: Path, source_root: Path) -> str:
    module_name = _module_name(path, source_root)
    if path.name == "__init__.py":
        return module_name
    return module_name.rpartition(".")[0]


def _imported_modules(
    node: ast.Import | ast.ImportFrom,
    *,
    package_name: str,
) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)

    module_name = node.module or ""
    if node.level:
        try:
            module_name = importlib.util.resolve_name(
                f"{'.' * node.level}{module_name}", package_name
            )
        except (ImportError, ValueError):
            return ("<invalid-relative-import>",)

    imports = [
        f"{module_name}.{alias.name}" if module_name else alias.name
        for alias in node.names
        if alias.name != "*"
    ]
    return tuple(imports) if imports else (module_name,)


def _layer(module_name: str) -> str | None:
    parts = module_name.split(".")
    if len(parts) >= 2 and parts[0] == "alpha_defense":
        return parts[1]
    return None


def _feature(module_name: str, layer: str) -> str | None:
    parts = module_name.split(".")
    if len(parts) >= 3 and parts[:2] == ["alpha_defense", layer]:
        return parts[2]
    return None


def _reason_for_violation(source_module: str, imported_module: str) -> str | None:
    source_layer = _layer(source_module)
    if source_layer not in _ALLOWED_INTERNAL_LAYERS:
        return None

    imported_root = imported_module.partition(".")[0]
    imported_layer = _layer(imported_module)
    if imported_root == "alpha_defense":
        if imported_layer is None:
            return None
        if imported_layer not in _ALLOWED_INTERNAL_LAYERS[source_layer]:
            return f"{source_layer} must not import {imported_layer}"

        source_feature = _feature(source_module, source_layer)
        imported_feature = _feature(imported_module, imported_layer)
        if (
            source_layer == imported_layer == "domain"
            and source_feature
            and imported_feature not in {source_feature, "shared", None}
        ):
            return "domain features must not import sibling domain features"
        if source_layer == imported_layer == "application" and source_feature != "workflows":
            allowed_features = {source_feature, "shared", "ports", None}
            if source_feature and imported_feature not in allowed_features:
                return "application features must be coordinated by workflows"
        return None

    if imported_root in _STDLIB_ROOTS:
        return None
    if source_layer in {"domain", "application"}:
        return f"{source_layer} must not import external package {imported_root}"
    if source_layer == "transport" and imported_root not in {"fastapi", "pydantic", "starlette"}:
        return f"transport must not import infrastructure package {imported_root}"
    return None


def find_import_violations(source_root: Path) -> tuple[ImportViolation, ...]:
    violations: set[ImportViolation] = set()
    for path in sorted(source_root.rglob("*.py")):
        source_module = _module_name(path, source_root)
        package_name = _package_name(path, source_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported_module in _imported_modules(node, package_name=package_name):
                reason = _reason_for_violation(source_module, imported_module)
                if reason is not None:
                    violations.add(ImportViolation(path, node.lineno, imported_module, reason))
    return tuple(sorted(violations))


def test_current_backend_tree_respects_import_boundaries() -> None:
    violations = find_import_violations(SOURCE_ROOT)

    assert violations == (), "\n".join(
        f"{violation.path}:{violation.line}: {violation.reason} ({violation.imported_module})"
        for violation in violations
    )


def test_forbidden_dependency_is_detected_and_removed(tmp_path: Path) -> None:
    probe = tmp_path / "alpha_defense" / "domain" / "shared" / "probe.py"
    probe.parent.mkdir(parents=True)
    probe.write_text("from alpha_defense.infrastructure import persistence\n", encoding="utf-8")

    violations = find_import_violations(tmp_path)

    assert len(violations) == 1
    assert violations[0].reason == "domain must not import infrastructure"

    probe.write_text("from dataclasses import dataclass\n", encoding="utf-8")

    assert find_import_violations(tmp_path) == ()


@pytest.mark.parametrize(
    ("relative_path", "source", "expected_reason"),
    [
        (
            "alpha_defense/application/shared/probe.py",
            "import sqlalchemy\n",
            "application must not import external package sqlalchemy",
        ),
        (
            "alpha_defense/domain/identity/probe.py",
            "from alpha_defense.domain.transfers import intent\n",
            "domain features must not import sibling domain features",
        ),
        (
            "alpha_defense/transport/probe.py",
            "import sqlalchemy\n",
            "transport must not import infrastructure package sqlalchemy",
        ),
    ],
)
def test_additional_forbidden_dependencies_are_detected(
    tmp_path: Path,
    relative_path: str,
    source: str,
    expected_reason: str,
) -> None:
    probe = tmp_path / relative_path
    probe.parent.mkdir(parents=True)
    probe.write_text(source, encoding="utf-8")

    violations = find_import_violations(tmp_path)

    assert any(violation.reason == expected_reason for violation in violations)
