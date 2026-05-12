from __future__ import annotations

from niri_state.selectors import workspaces
from tests._typing_helpers import make_minimal_snapshot


class TestWorkspaceSelectors:
    def test_list_workspaces_empty(self) -> None:
        snap = make_minimal_snapshot()
        result = workspaces.list_workspaces(snap)
        assert result == []

    def test_get_workspace_not_found(self) -> None:
        snap = make_minimal_snapshot()
        result = workspaces.get_workspace(snap, 999)
        assert result is None

    def test_get_focused_workspace_none(self) -> None:
        snap = make_minimal_snapshot()
        result = workspaces.get_focused_workspace(snap)
        assert result is None

    def test_get_active_workspace_on_output_none(self) -> None:
        snap = make_minimal_snapshot()
        result = workspaces.get_active_workspace_on_output(snap, "DP-1")
        assert result is None
