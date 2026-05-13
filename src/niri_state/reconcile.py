from __future__ import annotations

from niri_state.diagnostics import with_note
from niri_state.engine_state import EngineState
from niri_state.health import HealthState


def reconcile(engine: EngineState) -> None:
    _reconcile_focused_window(engine)
    _reconcile_focused_workspace(engine)
    _reconcile_keyboard(engine)
    _reconcile_workspace_window_relationships(engine)
    _reconcile_diagnostics(engine)


def _reconcile_focused_window(engine: EngineState) -> None:
    if engine.focused_window_id is None:
        return

    win = engine.windows.get(engine.focused_window_id)
    if win is None:
        engine.focused_window_id = None
        return

    if win.workspace_id is not None:
        engine.focused_workspace_id = win.workspace_id


def _reconcile_focused_workspace(engine: EngineState) -> None:
    if engine.focused_workspace_id is not None and engine.focused_workspace_id not in engine.workspaces:
        engine.focused_workspace_id = None

    if engine.focused_workspace_id is not None:
        return

    for workspace_id, ws in engine.workspaces.items():
        if ws.is_focused:
            engine.focused_workspace_id = workspace_id
            return


def _reconcile_keyboard(engine: EngineState) -> None:
    if engine.keyboard_layouts is None:
        return

    names = engine.keyboard_layouts.names
    idx = engine.keyboard_layouts.current_idx
    if names and not (0 <= idx < len(names)):
        engine.keyboard_layouts = engine.keyboard_layouts.model_copy(update={"current_idx": 0})


def _reconcile_workspace_window_relationships(engine: EngineState) -> None:
    for workspace_id, workspace in list(engine.workspaces.items()):
        active_window_id = workspace.active_window_id
        if active_window_id is None:
            continue
        window = engine.windows.get(active_window_id)
        if window is None or window.workspace_id != workspace_id:
            engine.workspaces[workspace_id] = workspace.model_copy(update={"active_window_id": None})


def _reconcile_diagnostics(engine: EngineState) -> None:
    if engine.health is HealthState.LIVE and engine.diagnostics.desynced:
        engine.diagnostics = engine.diagnostics.model_copy(update={"desynced": False})
    if engine.health is HealthState.STALE and not engine.diagnostics.desynced:
        engine.diagnostics = with_note(
            engine.diagnostics,
            note="health is stale without explicit desync marker",
        )
