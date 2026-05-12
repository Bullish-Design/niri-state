from __future__ import annotations

from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._core.models.types import WindowId, WorkspaceId


def get_window(snapshot: NiriSnapshot, window_id: WindowId) -> object | None:
    """Get window by id."""
    return snapshot.windows.get(window_id)


def get_windows_on_workspace(snapshot: NiriSnapshot, workspace_id: WorkspaceId) -> tuple[object, ...]:
    """Get all windows on a given workspace (excludes floating windows with workspace_id=None)."""
    win_ids = snapshot.windows_by_workspace.get(workspace_id, ())
    return tuple(snapshot.windows[wid] for wid in win_ids if wid in snapshot.windows)


def get_floating_windows(snapshot: NiriSnapshot) -> tuple[object, ...]:
    """Get all floating windows (windows with workspace_id=None)."""
    return tuple(win for win in snapshot.windows.values() if win.protocol.workspace_id is None)


def list_windows(snapshot: NiriSnapshot) -> list[object]:
    """List all windows."""
    return list(snapshot.windows.values())
