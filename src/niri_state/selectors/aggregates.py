from __future__ import annotations

from typing import TypedDict, cast

from niri_state._core.models.entities import WindowState, WorkspaceState
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._core.models.types import OutputName


class WorkspaceTreeNode(TypedDict):
    workspace: WorkspaceState
    windows: tuple[WindowState, ...]


class FocusedContext(TypedDict, total=False):
    focused_output_name: OutputName | None
    focused_workspace_id: int | None
    focused_window_id: int | None
    active_workspace_on_output: WorkspaceState | None
    focused_workspace: WorkspaceState | None
    focused_window: WindowState | None


def get_workspace_tree(snapshot: NiriSnapshot, output_name: OutputName) -> dict[str, WorkspaceTreeNode]:
    """Get a combined view of workspaces and their windows for an output."""
    ws_ids = snapshot.workspaces_by_output.get(output_name, ())
    result: dict[str, WorkspaceTreeNode] = {}
    for ws_id in ws_ids:
        ws = snapshot.workspaces.get(ws_id)
        if ws is not None:
            win_ids = snapshot.windows_by_workspace.get(ws_id, ())
            result[str(ws_id)] = {
                "workspace": ws,
                "windows": tuple(snapshot.windows[wid] for wid in win_ids if wid in snapshot.windows),
            }
    return result


def get_focused_context(snapshot: NiriSnapshot) -> FocusedContext:
    """Get the complete focus context."""
    output_name = snapshot.focused_output_name
    workspace_id = snapshot.focused_workspace_id
    window_id = snapshot.focused_window_id

    ctx = cast(FocusedContext, {})
    ctx["focused_output_name"] = output_name
    ctx["focused_workspace_id"] = workspace_id
    ctx["focused_window_id"] = window_id

    if output_name is not None:
        active_ws = snapshot.active_workspace_by_output.get(output_name)
        if active_ws is not None:
            ctx["active_workspace_on_output"] = snapshot.workspaces.get(active_ws)

    if workspace_id is not None:
        ctx["focused_workspace"] = snapshot.workspaces.get(workspace_id)

    if window_id is not None:
        ctx["focused_window"] = snapshot.windows.get(window_id)

    return ctx


def get_urgent_items(snapshot: NiriSnapshot) -> dict[str, tuple[WorkspaceState, ...] | tuple[WindowState, ...]]:
    """Get all urgent workspaces and windows."""
    urgent_workspaces = tuple(ws for ws in snapshot.workspaces.values() if ws.protocol.is_urgent)
    urgent_windows = tuple(win for win in snapshot.windows.values() if win.protocol.is_urgent)
    return {
        "workspaces": urgent_workspaces,
        "windows": urgent_windows,
    }
