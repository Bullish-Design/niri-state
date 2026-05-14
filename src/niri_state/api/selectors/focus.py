from __future__ import annotations

from niri_state.adapters.protocol import Window, Workspace
from niri_state.api.snapshot import Snapshot


def get_focused_window_id(snapshot: Snapshot) -> int | None:
    return snapshot.focused_window_id


def get_focused_workspace_id(snapshot: Snapshot) -> int | None:
    return snapshot.focused_workspace_id


def get_focused_output_name(snapshot: Snapshot) -> str | None:
    return snapshot.focused_output_name


def get_focused_window(snapshot: Snapshot) -> Window | None:
    if snapshot.focused_window_id is None:
        return None
    return snapshot.windows.get(snapshot.focused_window_id)


def get_focused_workspace(snapshot: Snapshot) -> Workspace | None:
    if snapshot.focused_workspace_id is None:
        return None
    return snapshot.workspaces.get(snapshot.focused_workspace_id)
