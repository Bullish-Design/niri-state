from __future__ import annotations

from niri_pypc.types.generated.event import (
    WorkspaceActivatedEvent,
    WorkspaceActiveWindowChangedEvent,
    WorkspacesChangedEvent,
    WorkspaceUrgencyChangedEvent,
)

from niri_state._core.models.draft import DraftState
from niri_state._core.models.entities import WorkspaceState


def apply_workspaces_changed(draft: DraftState, event: WorkspacesChangedEvent) -> bool:
    """Full replacement of workspace map."""
    new_workspaces = {ws.id: WorkspaceState(workspace_id=ws.id, protocol=ws) for ws in event.workspaces}
    changed = draft.workspaces != new_workspaces
    draft.workspaces = new_workspaces
    return changed


def apply_workspace_activated(draft: DraftState, event: WorkspaceActivatedEvent) -> bool:
    """Set target workspace is_active=True; clear is_active from others on same output.

    If focused=True, update is_focused and draft.focused_workspace_id.
    """
    changed = False

    target_ws_id = event.id
    target_output = None
    if target_ws_id in draft.workspaces:
        target_ws = draft.workspaces[target_ws_id]
        target_output = target_ws.protocol.output
        if not target_ws.protocol.is_active:
            updated_protocol = target_ws.protocol.model_copy(
                update={"is_active": True}  # type: ignore[arg-type]
            )
            draft.workspaces[target_ws_id] = target_ws.model_copy(
                update={"protocol": updated_protocol}  # type: ignore[arg-type]
            )
            changed = True

    for ws_id, ws in draft.workspaces.items():
        if ws_id == target_ws_id:
            continue
        if target_output is not None and ws.protocol.output == target_output and ws.protocol.is_active:
            updated_protocol = ws.protocol.model_copy(update={"is_active": False})
            draft.workspaces[ws_id] = ws.model_copy(update={"protocol": updated_protocol})
            changed = True

    if event.focused:
        for ws_id, ws in draft.workspaces.items():
            new_focused = ws_id == target_ws_id
            if ws.protocol.is_focused != new_focused:
                updated_protocol = ws.protocol.model_copy(update={"is_focused": new_focused})
                draft.workspaces[ws_id] = ws.model_copy(update={"protocol": updated_protocol})
                changed = True
        if target_ws_id in draft.workspaces:
            if draft.focused_workspace_id != target_ws_id:
                draft.focused_workspace_id = target_ws_id
                changed = True

    return changed


def apply_workspace_active_window_changed(draft: DraftState, event: WorkspaceActiveWindowChangedEvent) -> bool:
    """Patch target workspace active_window_id."""
    if event.workspace_id not in draft.workspaces:
        return False
    old = draft.workspaces[event.workspace_id]
    if old.protocol.active_window_id == event.active_window_id:
        return False
    updated_protocol = old.protocol.model_copy(
        update={"active_window_id": event.active_window_id}  # type: ignore[arg-type]
    )
    draft.workspaces[event.workspace_id] = old.model_copy(
        update={"protocol": updated_protocol}  # type: ignore[arg-type]
    )
    return True


def apply_workspace_urgency_changed(draft: DraftState, event: WorkspaceUrgencyChangedEvent) -> bool:
    """Patch is_urgent."""
    if event.id not in draft.workspaces:
        return False
    old = draft.workspaces[event.id]
    if old.protocol.is_urgent == event.urgent:
        return False
    updated_protocol = old.protocol.model_copy(
        update={"is_urgent": event.urgent}  # type: ignore[arg-type]
    )
    draft.workspaces[event.id] = old.model_copy(
        update={"protocol": updated_protocol}  # type: ignore[arg-type]
    )
    return True
