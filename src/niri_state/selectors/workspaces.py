from __future__ import annotations

from niri_state._core.models.entities import WorkspaceState
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._core.models.types import OutputName, WorkspaceId


def get_workspace(snapshot: NiriSnapshot, workspace_id: WorkspaceId) -> WorkspaceState | None:
    """Get workspace by id."""
    return snapshot.workspaces.get(workspace_id)


def get_focused_workspace(snapshot: NiriSnapshot) -> WorkspaceState | None:
    """Get the focused workspace."""
    if snapshot.focused_workspace_id is None:
        return None
    return snapshot.workspaces.get(snapshot.focused_workspace_id)


def get_workspaces_on_output(snapshot: NiriSnapshot, output_name: OutputName) -> tuple[WorkspaceState, ...]:
    """Get all workspaces on a given output."""
    ws_ids = snapshot.workspaces_by_output.get(output_name, ())
    return tuple(snapshot.workspaces[wid] for wid in ws_ids if wid in snapshot.workspaces)


def get_active_workspace_on_output(snapshot: NiriSnapshot, output_name: OutputName) -> WorkspaceState | None:
    """Get the active workspace on a given output."""
    ws_id = snapshot.active_workspace_by_output.get(output_name)
    if ws_id is None:
        return None
    return snapshot.workspaces.get(ws_id)


def list_workspaces(snapshot: NiriSnapshot) -> list[WorkspaceState]:
    """List all workspaces."""
    return list(snapshot.workspaces.values())
