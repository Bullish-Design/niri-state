from __future__ import annotations

from niri_state._core.models.snapshot import NiriSnapshot


def collect_invariant_violations(snapshot: NiriSnapshot) -> tuple[str, ...]:
    """Collect all invariant violations in a snapshot."""
    violations: list[str] = []

    for output_name, output_state in snapshot.outputs.items():
        if output_state.output_name != output_name:
            violations.append(f"Output key mismatch: key={output_name}, output_name={output_state.output_name}")

    for ws_id, ws_state in snapshot.workspaces.items():
        if ws_state.workspace_id != ws_id:
            violations.append(f"Workspace key mismatch: key={ws_id}, workspace_id={ws_state.workspace_id}")

    for win_id, win_state in snapshot.windows.items():
        if win_state.window_id != win_id:
            violations.append(f"Window key mismatch: key={win_id}, window_id={win_state.window_id}")

    if snapshot.focused_workspace_id is not None:
        if snapshot.focused_workspace_id not in snapshot.workspaces:
            violations.append(f"focused_workspace_id {snapshot.focused_workspace_id} references non-existent workspace")

    if snapshot.focused_window_id is not None:
        if snapshot.focused_window_id not in snapshot.windows:
            violations.append(f"focused_window_id {snapshot.focused_window_id} references non-existent window")

    if snapshot.focused_window_id is not None and snapshot.focused_workspace_id is not None:
        focused_window = snapshot.windows.get(snapshot.focused_window_id)
        if focused_window is not None and focused_window.protocol.workspace_id is not None:
            if focused_window.protocol.workspace_id != snapshot.focused_workspace_id:
                violations.append(
                    f"focused_window workspace_id ({focused_window.protocol.workspace_id}) "
                    f"doesn't match focused_workspace_id ({snapshot.focused_workspace_id})"
                )

    for ws_id, ws_state in snapshot.workspaces.items():
        if ws_state.protocol.active_window_id is not None:
            if ws_state.protocol.active_window_id not in snapshot.windows:
                violations.append(
                    f"Workspace {ws_id} active_window_id {ws_state.protocol.active_window_id} "
                    f"references non-existent window"
                )

    for win_id, win_state in snapshot.windows.items():
        if win_state.protocol.workspace_id is not None:
            if win_state.protocol.workspace_id not in snapshot.workspaces:
                violations.append(
                    f"Window {win_id} workspace_id {win_state.protocol.workspace_id} references non-existent workspace"
                )

    for output_name, ws_ids in snapshot.workspaces_by_output.items():
        seen_ws_ids: set[int] = set()
        for ws_id in ws_ids:
            if ws_id in seen_ws_ids:
                violations.append(f"Duplicate workspace id {ws_id} in workspaces_by_output[{output_name}]")
            seen_ws_ids.add(ws_id)

            if ws_id not in snapshot.workspaces:
                violations.append(f"workspaces_by_output[{output_name}] references non-existent workspace {ws_id}")
                continue

            ws = snapshot.workspaces[ws_id]
            if ws.protocol.output != output_name:
                violations.append(
                    f"workspaces_by_output[{output_name}] contains workspace {ws_id} with output {ws.protocol.output}"
                )

    for ws_id, win_ids in snapshot.windows_by_workspace.items():
        seen_win_ids: set[int] = set()
        for win_id in win_ids:
            if win_id in seen_win_ids:
                violations.append(f"Duplicate window id {win_id} in windows_by_workspace[{ws_id}]")
            seen_win_ids.add(win_id)

            if win_id not in snapshot.windows:
                violations.append(f"windows_by_workspace[{ws_id}] references non-existent window {win_id}")
                continue

            win = snapshot.windows[win_id]
            if win.protocol.workspace_id != ws_id:
                violations.append(
                    f"windows_by_workspace[{ws_id}] contains window {win_id} "
                    f"with workspace_id {win.protocol.workspace_id}"
                )

    for output_name, ws_id in snapshot.active_workspace_by_output.items():
        if ws_id not in snapshot.workspaces:
            violations.append(f"active_workspace_by_output[{output_name}] references non-existent workspace {ws_id}")
            continue

        ws = snapshot.workspaces[ws_id]
        if ws.protocol.output != output_name:
            violations.append(
                f"active_workspace_by_output[{output_name}] points to workspace {ws_id} "
                f"with output {ws.protocol.output}"
            )
        if not ws.protocol.is_active:
            violations.append(f"active_workspace_by_output[{output_name}] points to non-active workspace {ws_id}")

    return tuple(violations)


def assert_invariants(snapshot: NiriSnapshot) -> None:
    """Assert that all invariants hold for a snapshot."""
    violations = collect_invariant_violations(snapshot)
    if violations:
        from niri_state.errors import InvariantError

        raise InvariantError(
            "Snapshot invariants violated",
            violations=violations,
            revision=snapshot.revision,
        )
