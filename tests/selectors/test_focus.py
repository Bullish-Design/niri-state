from __future__ import annotations

from niri_state.selectors import focus
from tests._typing_helpers import make_minimal_snapshot


class TestFocusSelectors:
    def test_get_focused_window_id_none(self) -> None:
        snap = make_minimal_snapshot()
        result = focus.get_focused_window_id(snap)
        assert result is None

    def test_get_focused_workspace_id_none(self) -> None:
        snap = make_minimal_snapshot()
        result = focus.get_focused_workspace_id(snap)
        assert result is None

    def test_get_focused_output_name_none(self) -> None:
        snap = make_minimal_snapshot()
        result = focus.get_focused_output_name(snap)
        assert result is None

    def test_get_focused_window_returns_none_when_no_id(self) -> None:
        snap = make_minimal_snapshot()
        result = focus.get_focused_window(snap)
        assert result is None
