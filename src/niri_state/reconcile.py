from __future__ import annotations

from niri_state.engine_state import EngineState


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
    if (
        engine.focused_workspace_id is not None
        and engine.focused_workspace_id not in engine.workspaces
    ):
        engine.focused_workspace_id = None

    if engine.focused_workspace_id is not None:
        return

    for workspace_id, ws in engine.workspaces.items():
        if ws.is_focused:
            engine.focused_workspace_id = workspace_id
            return


def _reconcile_keyboard(engine: EngineState) -> None:
    return


def _reconcile_workspace_window_relationships(engine: EngineState) -> None:
    return


def _reconcile_diagnostics(engine: EngineState) -> None:
    return
