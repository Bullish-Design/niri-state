from __future__ import annotations

from niri_state._core.models.entities import OutputState, WorkspaceState
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._core.models.types import OutputName


def get_output(snapshot: NiriSnapshot, name: OutputName) -> OutputState | None:
    """Get output by name."""
    return snapshot.outputs.get(name)


def list_outputs(snapshot: NiriSnapshot) -> list[OutputState]:
    """List all outputs."""
    return list(snapshot.outputs.values())


def get_active_workspace_for_output(snapshot: NiriSnapshot, output_name: OutputName) -> WorkspaceState | None:
    """Get the active workspace for a given output."""
    ws_id = snapshot.active_workspace_by_output.get(output_name)
    if ws_id is None:
        return None
    return snapshot.workspaces.get(ws_id)


def get_workspaces_on_output(snapshot: NiriSnapshot, output_name: OutputName) -> tuple[WorkspaceState, ...]:
    """Get all workspaces on a given output."""
    ws_ids = snapshot.workspaces_by_output.get(output_name, ())
    return tuple(snapshot.workspaces[wid] for wid in ws_ids if wid in snapshot.workspaces)
