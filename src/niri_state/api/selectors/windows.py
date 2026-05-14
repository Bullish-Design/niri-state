from __future__ import annotations

from niri_state.protocol import Window
from niri_state.snapshot import Snapshot


def get_window(snapshot: Snapshot, window_id: int) -> Window | None:
    return snapshot.windows.get(window_id)


def list_windows(snapshot: Snapshot) -> tuple[Window, ...]:
    return tuple(snapshot.windows.values())


def list_windows_on_workspace(snapshot: Snapshot, workspace_id: int) -> tuple[Window, ...]:
    ids = snapshot.windows_by_workspace.get(workspace_id, ())
    return tuple(snapshot.windows[window_id] for window_id in ids)


def list_floating_windows(snapshot: Snapshot) -> tuple[Window, ...]:
    return tuple(window for window in snapshot.windows.values() if window.is_floating)
