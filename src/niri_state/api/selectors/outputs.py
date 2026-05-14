from __future__ import annotations

from niri_state.adapters.protocol import Output, Workspace
from niri_state.api.snapshot import Snapshot


def get_output(snapshot: Snapshot, output_name: str) -> Output | None:
    return snapshot.outputs.get(output_name)


def list_outputs(snapshot: Snapshot) -> tuple[Output, ...]:
    return tuple(snapshot.outputs.values())


def get_workspaces_on_output(snapshot: Snapshot, output_name: str) -> tuple[Workspace, ...]:
    ids = snapshot.workspaces_by_output.get(output_name, ())
    return tuple(snapshot.workspaces[workspace_id] for workspace_id in ids)


def get_active_workspace_for_output(snapshot: Snapshot, output_name: str) -> Workspace | None:
    workspace_id = snapshot.active_workspace_by_output.get(output_name)
    if workspace_id is None:
        return None
    return snapshot.workspaces.get(workspace_id)
