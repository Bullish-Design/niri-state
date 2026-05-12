from __future__ import annotations

import time
from types import MappingProxyType

from niri_state._core.models.entities import (
    KeyboardState,
    OutputState,
    OverviewState,
    WindowState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import (
    CompatibilityInfo,
    DiagnosticsInfo,
    NiriSnapshot,
)
from niri_state._core.models.types import (
    OutputName,
    Revision,
    WindowId,
    WorkspaceId,
)


class DraftState:
    """Mutable state representation for reducers.

    Reducers modify entity maps, focus pointers, and domain state on this
    object. Call freeze() to produce an immutable NiriSnapshot for publication.
    """

    def __init__(
        self,
        *,
        outputs: dict[OutputName, OutputState],
        workspaces: dict[WorkspaceId, WorkspaceState],
        windows: dict[WindowId, WindowState],
        focused_output_name: OutputName | None,
        focused_workspace_id: WorkspaceId | None,
        focused_window_id: WindowId | None,
        keyboard: KeyboardState,
        overview: OverviewState,
        health: HealthState,
        diagnostics: DiagnosticsInfo,
        compatibility: CompatibilityInfo,
    ) -> None:
        self.outputs = outputs
        self.workspaces = workspaces
        self.windows = windows
        self.focused_output_name = focused_output_name
        self.focused_workspace_id = focused_workspace_id
        self.focused_window_id = focused_window_id
        self.keyboard = keyboard
        self.overview = overview
        self.health = health
        self.diagnostics = diagnostics
        self.compatibility = compatibility

    @classmethod
    def from_snapshot(cls, snapshot: NiriSnapshot) -> DraftState:
        """Create a mutable draft from a published snapshot."""
        return cls(
            outputs=dict(snapshot.outputs),
            workspaces=dict(snapshot.workspaces),
            windows=dict(snapshot.windows),
            focused_output_name=snapshot.focused_output_name,
            focused_workspace_id=snapshot.focused_workspace_id,
            focused_window_id=snapshot.focused_window_id,
            keyboard=snapshot.keyboard,
            overview=snapshot.overview,
            health=snapshot.health,
            diagnostics=snapshot.diagnostics,
            compatibility=snapshot.compatibility,
        )

    def build_indexes(
        self,
    ) -> tuple[
        dict[OutputName, tuple[WorkspaceId, ...]],
        dict[WorkspaceId, tuple[WindowId, ...]],
        dict[OutputName, WorkspaceId],
    ]:
        """Compute derived indexes from current entity maps."""
        workspaces_by_output: dict[OutputName, list[WorkspaceId]] = {}
        active_workspace_by_output: dict[OutputName, WorkspaceId] = {}
        for ws_id, ws in self.workspaces.items():
            output = ws.protocol.output
            if output is not None:
                workspaces_by_output.setdefault(output, []).append(ws_id)
                if ws.protocol.is_active:
                    active_workspace_by_output[output] = ws_id

        windows_by_workspace: dict[WorkspaceId, list[WindowId]] = {}
        for win_id, win in self.windows.items():
            ws_id = win.protocol.workspace_id
            if ws_id is not None:
                windows_by_workspace.setdefault(ws_id, []).append(win_id)

        return (
            {k: tuple(sorted(v)) for k, v in workspaces_by_output.items()},
            {k: tuple(sorted(v)) for k, v in windows_by_workspace.items()},
            active_workspace_by_output,
        )

    def freeze(self, *, revision: Revision, force_health: HealthState | None = None) -> NiriSnapshot:
        """Freeze draft into an immutable published snapshot."""
        ws_by_output, win_by_ws, active_ws = self.build_indexes()
        health = force_health if force_health is not None else self.health

        return NiriSnapshot(
            revision=revision,
            timestamp=time.monotonic(),
            health=health,
            outputs=MappingProxyType(dict(self.outputs)),
            workspaces=MappingProxyType(dict(self.workspaces)),
            windows=MappingProxyType(dict(self.windows)),
            focused_output_name=self.focused_output_name,
            focused_workspace_id=self.focused_workspace_id,
            focused_window_id=self.focused_window_id,
            keyboard=self.keyboard,
            overview=self.overview,
            workspaces_by_output=MappingProxyType(ws_by_output),
            windows_by_workspace=MappingProxyType(win_by_ws),
            active_workspace_by_output=MappingProxyType(active_ws),
            diagnostics=self.diagnostics,
            compatibility=self.compatibility,
        )
