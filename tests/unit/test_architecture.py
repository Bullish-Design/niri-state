"""Tests to verify architectural layering and dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path


def get_imports(file_path: Path) -> set[str]:
    """Extract all imported module names from a Python file."""
    try:
        source = file_path.read_text()
    except Exception:
        return set()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)

    return imports


def get_all_py_files(package_path: Path) -> list[Path]:
    """Get all Python files in a package recursively."""
    return list(package_path.rglob("*.py"))


class TestArchitecture:
    """Test architectural constraints."""

    def test_adapters_cannot_import_core(self) -> None:
        """Adapters package should not import from core package."""
        adapters_path = Path("src/niri_state/adapters")
        if not adapters_path.exists():
            return

        forbidden_imports = {"niri_state.core"}
        for py_file in get_all_py_files(adapters_path):
            imports = get_imports(py_file)
            violations = imports & forbidden_imports
            assert not violations, f"{py_file} imports from core: {violations}"

    def test_observability_cannot_import_api_or_core(self) -> None:
        """Observability package should not import from api or core packages."""
        obs_path = Path("src/niri_state/observability")
        if not obs_path.exists():
            return

        forbidden_imports = {"niri_state.api", "niri_state.core", "niri_state.api.state"}
        for py_file in get_all_py_files(obs_path):
            imports = get_imports(py_file)
            violations = imports & forbidden_imports
            assert not violations, f"{py_file} imports from api/core: {violations}"

    def test_api_should_not_import_from_top_level_shims(self) -> None:
        """API package should import from canonical paths, not top-level shims."""
        api_path = Path("src/niri_state/api")
        if not api_path.exists():
            return

        # These are the shim modules at top level that API should not use
        shim_modules = {
            "niri_state.store",
            "niri_state.bootstrap",
            "niri_state.broadcaster",
            "niri_state.diagnostics",
            "niri_state.engine_state",
            "niri_state.invariants",
            "niri_state.reconcile",
            "niri_state.reducers",
            "niri_state.resync",
        }

        for py_file in get_all_py_files(api_path):
            # Skip __init__.py files
            if py_file.name == "__init__.py":
                continue
            imports = get_imports(py_file)
            violations = imports & shim_modules
            assert not violations, f"{py_file} imports from top-level shims: {violations}"

    def test_api_errors_should_not_import_from_core(self) -> None:
        """api/errors.py should not import data types from core (they leak into public API)."""
        errors_file = Path("src/niri_state/api/errors.py")
        if not errors_file.exists():
            return

        imports = get_imports(errors_file)
        core_imports = {i for i in imports if i.startswith("niri_state.core")}
        assert not core_imports, f"api/errors.py imports from core: {core_imports}"
