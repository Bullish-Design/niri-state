from __future__ import annotations

from importlib import metadata
from pathlib import Path

import niri_state


def test_runtime_version_matches_package_metadata() -> None:
    assert metadata.version("niri-state") == niri_state.__version__


def test_package_includes_py_typed_marker() -> None:
    package_dir = Path(niri_state.__file__).resolve().parent
    assert (package_dir / "py.typed").is_file()
