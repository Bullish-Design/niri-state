from __future__ import annotations

import pytest

from niri_state.selectors import windows


def _make_minimal_snapshot(**overrides):
    """Build a minimal snapshot for testing."""
    from niri_state._core.models.entities import KeyboardState, OverviewState
    from niri_state._core.models.health import HealthState
    from niri_state._core.models.snapshot import (
        CompatibilityInfo,
        DiagnosticsInfo,
        NiriSnapshot,
    )
    from niri_pypc.types.generated.models import KeyboardLayouts

    defaults: dict[str, object] = dict(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_output_name=None,
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard=KeyboardState(
            protocol=KeyboardLayouts(current_idx=0, names=["us"]),
            current_name="us",
        ),
        overview=OverviewState(is_open=False),
        workspaces_by_output={},
        windows_by_workspace={},
        active_workspace_by_output={},
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(),
    )
    defaults.update(overrides)
    return NiriSnapshot(**defaults)  # type: ignore[arg-type]


class TestWindowSelectors:
    def test_list_windows_empty(self) -> None:
        snap = _make_minimal_snapshot()
        result = windows.list_windows(snap)
        assert result == []

    def test_get_window_not_found(self) -> None:
        snap = _make_minimal_snapshot()
        result = windows.get_window(snap, 999)
        assert result is None

    def test_get_windows_on_workspace_empty(self) -> None:
        snap = _make_minimal_snapshot()
        result = windows.get_windows_on_workspace(snap, 1)
        assert result == ()

    def test_get_floating_windows_empty(self) -> None:
        snap = _make_minimal_snapshot()
        result = windows.get_floating_windows(snap)
        assert result == ()

    def test_get_floating_windows_with_floating(self) -> None:
        from niri_state._core.models.entities import WindowState
        from niri_pypc.types.generated.models import Window

        ws_win = Window(
            id=100,
            workspace_id=1,
            is_focused=False,
            is_floating=False,
            is_urgent=False,
            layout={"tile_size": [100, 50], "window_offset_in_tile": [0, 0], "window_size": [100, 50]},
        )
        float_win = Window(
            id=200,
            workspace_id=None,
            is_focused=False,
            is_floating=True,
            is_urgent=False,
            layout={"tile_size": [100, 50], "window_offset_in_tile": [0, 0], "window_size": [100, 50]},
        )

        snap = _make_minimal_snapshot(
            windows={
                100: WindowState(window_id=100, protocol=ws_win),
                200: WindowState(window_id=200, protocol=float_win),
            }
        )
        result = windows.get_floating_windows(snap)
        assert len(result) == 1
        assert result[0].window_id == 200
