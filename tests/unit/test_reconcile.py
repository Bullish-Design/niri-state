from __future__ import annotations

from niri_state.engine_state import EngineState
from niri_state.reconcile import reconcile
from tests.factories.protocol import make_keyboard_layouts, make_overview, make_window, make_workspace


def test_reconcile_clears_missing_focused_window() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.focused_window_id = 999

    reconcile(engine)

    assert engine.focused_window_id is None


def test_reconcile_derives_focused_workspace_from_focused_window() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.workspaces = {1: make_workspace(id=1)}
    engine.windows = {100: make_window(id=100, workspace_id=1)}
    engine.focused_window_id = 100

    reconcile(engine)

    assert engine.focused_workspace_id == 1
