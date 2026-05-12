from __future__ import annotations

from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._core.models.types import OutputName, WindowId, WorkspaceId


def get_focused_output_name(snapshot: NiriSnapshot) -> OutputName | None:
    """Get the focused output name."""
    return snapshot.focused_output_name


def get_focused_workspace_id(snapshot: NiriSnapshot) -> WorkspaceId | None:
    """Get the focused workspace id."""
    return snapshot.focused_workspace_id


def get_focused_window_id(snapshot: NiriSnapshot) -> WindowId | None:
    """Get the focused window id."""
    return snapshot.focused_window_id


def get_focused_window(snapshot: NiriSnapshot) -> object | None:
    """Get the focused window."""
    if snapshot.focused_window_id is None:
        return None
    return snapshot.windows.get(snapshot.focused_window_id)
