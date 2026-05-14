from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from niri_state.adapters.protocol import Window, Workspace
from niri_state.api.snapshot import Snapshot


class FocusedContext(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    output_name: str | None
    workspace: Workspace | None
    window: Window | None


class WorkspaceTreeNode(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    workspace: Workspace
    windows: tuple[Window, ...]


def get_focused_context(snapshot: Snapshot) -> FocusedContext:
    workspace = None
    if snapshot.focused_workspace_id is not None:
        workspace = snapshot.workspaces.get(snapshot.focused_workspace_id)

    window = None
    if snapshot.focused_window_id is not None:
        window = snapshot.windows.get(snapshot.focused_window_id)

    return FocusedContext(
        output_name=snapshot.focused_output_name,
        workspace=workspace,
        window=window,
    )


def get_workspace_tree(snapshot: Snapshot, output_name: str) -> tuple[WorkspaceTreeNode, ...]:
    workspace_ids = snapshot.workspaces_by_output.get(output_name, ())
    nodes: list[WorkspaceTreeNode] = []

    for workspace_id in workspace_ids:
        workspace = snapshot.workspaces[workspace_id]
        window_ids = snapshot.windows_by_workspace.get(workspace_id, ())
        nodes.append(
            WorkspaceTreeNode(
                workspace=workspace,
                windows=tuple(snapshot.windows[window_id] for window_id in window_ids),
            )
        )

    return tuple(nodes)


def get_urgent_items(snapshot: Snapshot) -> tuple[Workspace | Window, ...]:
    items: list[Workspace | Window] = []
    items.extend(workspace for workspace in snapshot.workspaces.values() if workspace.is_urgent)
    items.extend(window for window in snapshot.windows.values() if window.is_urgent)
    return tuple(items)
