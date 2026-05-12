from __future__ import annotations

from dataclasses import dataclass

from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    Workspace,
)


@dataclass(frozen=True, slots=True)
class BootstrapPayload:
    """Normalized query results ready for initial snapshot construction.

    Populated by _runtime/bootstrap.py, consumed by _core/snapshot_builder.py.
    """

    outputs: dict[str, Output]
    workspaces: list[Workspace]
    windows: list[Window]
    focused_output: Output | None
    focused_window: Window | None
    keyboard_layouts: KeyboardLayouts
    overview: Overview
    compositor_version: str | None = None
