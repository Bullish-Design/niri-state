from __future__ import annotations

from tests.factories.protocol import make_keyboard_layouts, make_overview, make_window

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.selectors.focus import get_focused_window
from niri_state.snapshot import Snapshot


def test_get_focused_window_returns_window() -> None:
    window = make_window(id=100)
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={100: window},
        focused_workspace_id=None,
        focused_window_id=100,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert get_focused_window(snapshot) == window
