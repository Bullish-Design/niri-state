from __future__ import annotations

from niri_state.adapters.protocol import Workspace
from niri_state.api.snapshot import Snapshot


def get_workspace(snapshot: Snapshot, workspace_id: int) -> Workspace | None:
    return snapshot.workspaces.get(workspace_id)


def list_workspaces(snapshot: Snapshot) -> tuple[Workspace, ...]:
    return tuple(snapshot.workspaces.values())


def list_workspaces_on_output(snapshot: Snapshot, output_name: str) -> tuple[Workspace, ...]:
    ids = snapshot.workspaces_by_output.get(output_name, ())
    return tuple(snapshot.workspaces[workspace_id] for workspace_id in ids)


def get_active_workspace(snapshot: Snapshot, output_name: str) -> Workspace | None:
    workspace_id = snapshot.active_workspace_by_output.get(output_name)
    if workspace_id is None:
        return None
    return snapshot.workspaces.get(workspace_id)
