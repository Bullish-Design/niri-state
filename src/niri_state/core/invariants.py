from __future__ import annotations

from niri_state.api.errors import InvariantError
from niri_state.api.snapshot import Snapshot
from niri_state.api.types import InvariantViolation


def collect_invariant_violations(snapshot: Snapshot) -> tuple[InvariantViolation, ...]:
    violations: list[InvariantViolation] = []

    if snapshot.focused_window_id is not None and snapshot.focused_window_id not in snapshot.windows:
        violations.append(
            InvariantViolation(
                code="focused_window_missing",
                message="focused_window_id does not reference an existing window",
                path=("focused_window_id",),
            )
        )

    if snapshot.focused_workspace_id is not None and snapshot.focused_workspace_id not in snapshot.workspaces:
        violations.append(
            InvariantViolation(
                code="focused_workspace_missing",
                message="focused_workspace_id does not reference an existing workspace",
                path=("focused_workspace_id",),
            )
        )

    for window_id, win in snapshot.windows.items():
        if win.workspace_id is None:
            continue
        if win.workspace_id not in snapshot.workspaces:
            violations.append(
                InvariantViolation(
                    code="window_workspace_missing",
                    message="window references missing workspace",
                    path=("windows", window_id, "workspace_id"),
                )
            )

    for workspace_id, ws in snapshot.workspaces.items():
        if ws.output is None:
            continue
        if ws.output not in snapshot.outputs:
            violations.append(
                InvariantViolation(
                    code="workspace_output_missing",
                    message="workspace references missing output",
                    path=("workspaces", workspace_id, "output"),
                )
            )

    for output_name, workspace_id in snapshot.active_workspace_by_output.items():
        ws = snapshot.workspaces.get(workspace_id)
        if ws is None or ws.output != output_name or not ws.is_active:
            violations.append(
                InvariantViolation(
                    code="active_workspace_mismatch",
                    message="active_workspace_by_output is inconsistent with workspace state",
                    path=("active_workspace_by_output", output_name),
                )
            )

    for output_name, workspace_ids in snapshot.workspaces_by_output.items():
        ordered = sorted(
            (
                snapshot.workspaces[workspace_id]
                for workspace_id in workspace_ids
                if workspace_id in snapshot.workspaces
            ),
            key=lambda workspace: (workspace.idx, workspace.id),
        )
        expected = tuple(workspace.id for workspace in ordered)
        if workspace_ids != expected:
            violations.append(
                InvariantViolation(
                    code="workspaces_by_output_ordering",
                    message="workspaces_by_output ordering must be stable by (idx, id)",
                    path=("workspaces_by_output", output_name),
                )
            )

    for workspace_id, window_ids in snapshot.windows_by_workspace.items():
        expected = tuple(
            sorted(window.id for window in snapshot.windows.values() if window.workspace_id == workspace_id)
        )
        if window_ids != expected:
            violations.append(
                InvariantViolation(
                    code="windows_by_workspace_ordering",
                    message="windows_by_workspace ordering must be stable by window id",
                    path=("windows_by_workspace", workspace_id),
                )
            )

    return tuple(violations)


def assert_invariants(snapshot: Snapshot) -> None:
    violations = collect_invariant_violations(snapshot)
    if not violations:
        return

    raise InvariantError(
        "snapshot invariants violated",
        violations=violations,
        revision=snapshot.revision,
        operation="assert_invariants",
    )
