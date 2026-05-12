from __future__ import annotations

from niri_pypc.types.generated.event import (
    WindowClosedEvent,
    WindowFocusChangedEvent,
    WindowFocusTimestampChangedEvent,
    WindowLayoutsChangedEvent,
    WindowOpenedOrChangedEvent,
    WindowsChangedEvent,
    WindowUrgencyChangedEvent,
)

from niri_state._core.models.draft import DraftState
from niri_state._core.models.entities import WindowState


def apply_windows_changed(draft: DraftState, event: WindowsChangedEvent) -> bool:
    """Full replacement of window map."""
    new_windows = {win.id: WindowState(window_id=win.id, protocol=win) for win in event.windows}
    changed = draft.windows != new_windows
    draft.windows = new_windows
    return changed


def apply_window_opened_or_changed(draft: DraftState, event: WindowOpenedOrChangedEvent) -> bool:
    """Upsert window by id."""
    old_state = draft.windows.get(event.window.id)
    draft.windows[event.window.id] = WindowState(window_id=event.window.id, protocol=event.window)
    return old_state is None or old_state.protocol != event.window


def apply_window_closed(draft: DraftState, event: WindowClosedEvent) -> bool:
    """Remove window id if present."""
    removed = event.id in draft.windows
    if removed:
        del draft.windows[event.id]
    return removed


def apply_window_focus_changed(draft: DraftState, event: WindowFocusChangedEvent) -> bool:
    """Update focused_window_id; update focused_workspace_id from target window."""
    old_focused = draft.focused_window_id
    draft.focused_window_id = event.id

    if event.id is not None and event.id in draft.windows:
        win = draft.windows[event.id]
        draft.focused_workspace_id = win.protocol.workspace_id
    elif event.id is None:
        draft.focused_workspace_id = None

    return old_focused != draft.focused_window_id


def apply_window_urgency_changed(draft: DraftState, event: WindowUrgencyChangedEvent) -> bool:
    """Patch is_urgent."""
    if event.id not in draft.windows:
        return False
    old = draft.windows[event.id]
    updated_protocol = old.protocol.model_copy(
        update={"is_urgent": event.urgent}  # type: ignore[arg-type]
    )
    draft.windows[event.id] = old.model_copy(
        update={"protocol": updated_protocol}  # type: ignore[arg-type]
    )
    return old.protocol.is_urgent != event.urgent


def apply_window_focus_timestamp_changed(draft: DraftState, event: WindowFocusTimestampChangedEvent) -> bool:
    """Patch focus_timestamp."""
    if event.id not in draft.windows:
        return False
    old = draft.windows[event.id]
    updated_protocol = old.protocol.model_copy(
        update={"focus_timestamp": event.focus_timestamp}  # type: ignore[arg-type]
    )
    draft.windows[event.id] = old.model_copy(
        update={"protocol": updated_protocol}  # type: ignore[arg-type]
    )
    return old.protocol.focus_timestamp != event.focus_timestamp


def apply_window_layouts_changed(draft: DraftState, event: WindowLayoutsChangedEvent) -> bool:
    """Patch per-window layout from changes list."""
    changed = False
    for win_id, layout in event.changes:
        if win_id not in draft.windows:
            continue
        old = draft.windows[win_id]
        updated_protocol = old.protocol.model_copy(
            update={"layout": layout}  # type: ignore[arg-type]
        )
        if old.protocol.layout != updated_protocol.layout:
            draft.windows[win_id] = old.model_copy(
                update={"protocol": updated_protocol}  # type: ignore[arg-type]
            )
            changed = True
    return changed
