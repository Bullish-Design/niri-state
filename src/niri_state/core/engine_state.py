from __future__ import annotations

from dataclasses import dataclass, field
from time import time

from niri_state.adapters.protocol import KeyboardLayouts, Output, Overview, Window, Workspace
from niri_state.core.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.snapshot import Snapshot


@dataclass(slots=True)
class EngineState:
    outputs: dict[str, Output] = field(default_factory=dict)
    workspaces: dict[int, Workspace] = field(default_factory=dict)
    windows: dict[int, Window] = field(default_factory=dict)

    focused_workspace_id: int | None = None
    focused_window_id: int | None = None

    keyboard_layouts: KeyboardLayouts | None = None
    overview: Overview | None = None

    health: HealthState = HealthState.BOOTSTRAPPING
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    compatibility: Compatibility = field(default_factory=Compatibility)

    @classmethod
    def empty(cls) -> EngineState:
        return cls()

    def require_initialized(self) -> None:
        if self.keyboard_layouts is None:
            raise RuntimeError("engine_state.keyboard_layouts is not initialized")
        if self.overview is None:
            raise RuntimeError("engine_state.overview is not initialized")

    def freeze(self, *, revision: int, timestamp: float | None = None) -> Snapshot:
        self.require_initialized()
        return Snapshot(
            revision=revision,
            timestamp=time() if timestamp is None else timestamp,
            health=self.health,
            outputs=self.outputs,
            workspaces=self.workspaces,
            windows=self.windows,
            focused_workspace_id=self.focused_workspace_id,
            focused_window_id=self.focused_window_id,
            keyboard_layouts=self.keyboard_layouts,
            overview=self.overview,
            diagnostics=self.diagnostics,
            compatibility=self.compatibility,
        )
