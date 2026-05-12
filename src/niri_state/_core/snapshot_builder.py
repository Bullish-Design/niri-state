from __future__ import annotations

from niri_pypc.types.generated.models import KeyboardLayouts

from niri_state._core.models.bootstrap_payload import BootstrapPayload
from niri_state._core.models.draft import DraftState
from niri_state._core.models.entities import (
    KeyboardState,
    OutputState,
    OverviewState,
    WindowState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import CompatibilityInfo, DiagnosticsInfo


def _derive_keyboard_current_name(layouts: KeyboardLayouts) -> str | None:
    """Derive current keyboard layout name from protocol payload."""
    if layouts.current_idx < 0:
        return None
    if layouts.current_idx >= len(layouts.names):
        return None
    return layouts.names[layouts.current_idx]


def build_initial_draft(payload: BootstrapPayload) -> DraftState:
    """Build initial mutable draft from bootstrap payload."""
    outputs = {name: OutputState(output_name=name, protocol=output) for name, output in payload.outputs.items()}
    workspaces = {ws.id: WorkspaceState(workspace_id=ws.id, protocol=ws) for ws in payload.workspaces}
    windows = {win.id: WindowState(window_id=win.id, protocol=win) for win in payload.windows}

    focused_output_name = payload.focused_output.name if payload.focused_output else None  # type: ignore[possibly-unbound]
    focused_window_id = payload.focused_window.id if payload.focused_window else None  # type: ignore[possibly-unbound]

    focused_workspace_id = None
    if payload.focused_window is not None:
        focused_workspace_id = payload.focused_window.workspace_id  # type: ignore[possibly-unbound]
    if focused_workspace_id is None and focused_output_name is not None:
        for ws in payload.workspaces:
            if ws.output == focused_output_name and ws.is_focused:
                focused_workspace_id = ws.id
                break

    keyboard = KeyboardState(
        protocol=payload.keyboard_layouts,
        current_name=_derive_keyboard_current_name(payload.keyboard_layouts),
    )
    overview = OverviewState(is_open=payload.overview.is_open)

    return DraftState(
        outputs=outputs,
        workspaces=workspaces,
        windows=windows,
        focused_output_name=focused_output_name,
        focused_workspace_id=focused_workspace_id,
        focused_window_id=focused_window_id,
        keyboard=keyboard,
        overview=overview,
        health=HealthState.BOOTSTRAPPING,
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(compositor_version=payload.compositor_version),
    )
