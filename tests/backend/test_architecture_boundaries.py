from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path("apps/backend/backend")
APPLICATION_ROOT = BACKEND_ROOT / "application"
DOMAIN_ROOT = BACKEND_ROOT / "domain"
ROUTERS_ROOT = BACKEND_ROOT / "routers"

APPLICATION_COMPAT_ALLOWLIST = {
    APPLICATION_ROOT / "wordpack" / "generate_wordpack.py",
}

DOMAIN_FORBIDDEN_PREFIXES = (
    "fastapi",
    "starlette",
    "google.cloud",
    "firebase",
    "openai",
    "httpx",
    "requests",
    "backend.config",
    "backend.settings",
    "backend.store",
    "backend.infrastructure",
    "backend.routers",
    "backend.presentation",
)

APPLICATION_FORBIDDEN_PREFIXES = (
    "fastapi",
    "starlette",
    "google.cloud",
    "firebase",
    "openai",
    "httpx",
    "requests",
    "backend.config",
    "backend.settings",
    "backend.store",
    "backend.routers",
    "backend.presentation",
    "backend.infrastructure",
)


def _py_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _module_from_import(node: ast.AST, current_file: Path) -> str | None:
    if isinstance(node, ast.Import):
        return None
    if not isinstance(node, ast.ImportFrom):
        return None
    module = node.module or ""
    if node.level == 0:
        return module
    package_parts = current_file.with_suffix("").parts
    backend_index = package_parts.index("backend")
    current_package = list(package_parts[backend_index:-1])
    up_count = max(0, node.level - 1)
    if up_count:
        current_package = current_package[:-up_count]
    return ".".join([*current_package, module]).rstrip(".")


def _imported_modules(tree: ast.AST, current_file: Path) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _module_from_import(node, current_file)
            if module:
                modules.append(module)
    return modules


def _call_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                parts = [func.attr]
                value = func.value
                while isinstance(value, ast.Attribute):
                    parts.append(value.attr)
                    value = value.value
                if isinstance(value, ast.Name):
                    parts.append(value.id)
                names.append(".".join(reversed(parts)))
            elif isinstance(func, ast.Name):
                names.append(func.id)
    return names


def _violations(root: Path, forbidden: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    for path in _py_files(root):
        if path in APPLICATION_COMPAT_ALLOWLIST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree, path):
            if module == "backend.models" or module.startswith("backend.models."):
                continue
            if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden):
                violations.append(f"{path}: forbidden import {module}")
        if root == APPLICATION_ROOT:
            for call_name in _call_names(tree):
                if call_name in {"asyncio.create_task", "uuid.uuid4", "datetime.now"}:
                    violations.append(f"{path}: forbidden call {call_name}")
    return violations


def test_domain_layer_has_no_outer_dependencies() -> None:
    assert _violations(DOMAIN_ROOT, DOMAIN_FORBIDDEN_PREFIXES) == []


def test_application_layer_has_no_framework_store_or_infrastructure_dependencies() -> None:
    assert _violations(APPLICATION_ROOT, APPLICATION_FORBIDDEN_PREFIXES) == []


def test_router_legacy_dependency_resolution_does_not_use_sys_modules() -> None:
    violations: list[str] = []
    for path in _py_files(ROUTERS_ROOT):
        text = path.read_text(encoding="utf-8")
        if "sys.modules" in text:
            violations.append(str(path))
    assert violations == []
