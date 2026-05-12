from __future__ import annotations

from niri_state.selectors import windows
from tests._typing_helpers import make_minimal_snapshot


class TestWindowSelectors:
    def test_list_windows_empty(self) -> None:
        snap = make_minimal_snapshot()
        result = windows.list_windows(snap)
        assert result == []

    def test_get_window_not_found(self) -> None:
        snap = make_minimal_snapshot()
        result = windows.get_window(snap, 999)
        assert result is None

    def test_get_windows_on_workspace_empty(self) -> None:
        snap = make_minimal_snapshot()
        result = windows.get_windows_on_workspace(snap, 1)
        assert result == ()

    def test_get_floating_windows_empty(self) -> None:
        snap = make_minimal_snapshot()
        result = windows.get_floating_windows(snap)
        assert result == ()

    def test_get_floating_windows_with_floating(self) -> None:
        from niri_pypc.types.generated.models import Window, WindowLayout

        from niri_state._core.models.entities import WindowState

        layout = WindowLayout.model_validate(
            {"tile_size": [100, 50], "window_offset_in_tile": [0, 0], "window_size": [100, 50]}
        )
        ws_win = Window(
            id=100,
            workspace_id=1,
            is_focused=False,
            is_floating=False,
            is_urgent=False,
            layout=layout,
        )
        float_win = Window(
            id=200,
            workspace_id=None,
            is_focused=False,
            is_floating=True,
            is_urgent=False,
            layout=layout,
        )

        snap = make_minimal_snapshot(
            windows={
                100: WindowState(window_id=100, protocol=ws_win),
                200: WindowState(window_id=200, protocol=float_win),
            }
        )
        result = windows.get_floating_windows(snap)
        assert len(result) == 1
        assert result[0].window_id == 200
