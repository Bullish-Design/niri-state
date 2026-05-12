from __future__ import annotations

from typing import cast

import pytest
from niri_pypc.types.generated.models import KeyboardLayouts, Window, WindowLayout, Workspace

from niri_state._core.invariants import assert_invariants, collect_invariant_violations
from niri_state._core.models.draft import DraftState
from niri_state._core.models.entities import (
    KeyboardState,
    OverviewState,
    WindowState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import (
    CompatibilityInfo,
    DiagnosticsInfo,
)
from niri_state.errors import InvariantError


def _layout() -> WindowLayout:
    return WindowLayout.model_validate(
        {"tile_size": [100, 50], "window_offset_in_tile": [0, 0], "window_size": [100, 50]}
    )


def _make_valid_draft() -> DraftState:
    ws = Workspace(
        id=1, idx=0, name="1", output="DP-1", is_active=True, is_focused=True, is_urgent=False, active_window_id=None
    )
    win = Window(
        id=10,
        app_id="test",
        title="Test",
        workspace_id=1,
        is_focused=True,
        is_floating=False,
        is_urgent=False,
        pid=None,
        focus_timestamp=None,
        layout=_layout(),
    )
    return DraftState(
        outputs={"DP-1": type("OutputState", (), {"output_name": "DP-1", "protocol": None})()},
        workspaces={1: WorkspaceState(workspace_id=1, protocol=ws)},
        windows={10: WindowState(window_id=10, protocol=win)},
        focused_output_name="DP-1",
        focused_workspace_id=1,
        focused_window_id=10,
        keyboard=KeyboardState(protocol=KeyboardLayouts(current_idx=0, names=["us"]), current_name="us"),
        overview=OverviewState(is_open=False),
        health=HealthState.LIVE,
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(),
    )


class TestInvariants:
    def test_valid_snapshot_passes(self) -> None:
        draft = _make_valid_draft()
        snap = draft.freeze(revision=1)
        assert_invariants(snap)

    def test_focused_workspace_missing(self) -> None:
        draft = _make_valid_draft()
        draft.focused_workspace_id = 999
        snap = draft.freeze(revision=1)
        violations = collect_invariant_violations(snap)
        assert any("999" in v and "workspace" in v for v in violations)

    def test_focused_window_missing(self) -> None:
        draft = _make_valid_draft()
        draft.focused_window_id = 999
        snap = draft.freeze(revision=1)
        violations = collect_invariant_violations(snap)
        assert any("999" in v and "window" in v for v in violations)

    def test_workspace_key_mismatch(self) -> None:
        ws = Workspace(
            id=1,
            idx=0,
            name="1",
            output="DP-1",
            is_active=True,
            is_focused=True,
            is_urgent=False,
            active_window_id=None,
        )
        draft = _make_valid_draft()
        draft.workspaces[1] = WorkspaceState(workspace_id=2, protocol=ws)
        snap = draft.freeze(revision=1)
        violations = collect_invariant_violations(snap)
        assert any("mismatch" in v for v in violations)

    def test_window_workspace_reference_missing(self) -> None:
        win = Window(
            id=10,
            app_id="test",
            title="Test",
            workspace_id=999,
            is_focused=True,
            is_floating=False,
            is_urgent=False,
            pid=None,
            focus_timestamp=None,
            layout=_layout(),
        )
        draft = _make_valid_draft()
        draft.windows[10] = WindowState(window_id=10, protocol=win)
        snap = draft.freeze(revision=1)
        violations = collect_invariant_violations(snap)
        assert any("999" in v and "workspace" in v for v in violations)

    def test_workspace_active_window_reference_missing(self) -> None:
        ws = Workspace(
            id=1,
            idx=0,
            name="1",
            output="DP-1",
            is_active=True,
            is_focused=True,
            is_urgent=False,
            active_window_id=999,
        )
        draft = _make_valid_draft()
        draft.workspaces[1] = WorkspaceState(workspace_id=1, protocol=ws)
        snap = draft.freeze(revision=1)
        violations = collect_invariant_violations(snap)
        assert any("999" in v and "window" in v for v in violations)

    def test_assert_invariants_raises_on_violation(self) -> None:
        draft = _make_valid_draft()
        draft.focused_workspace_id = 999
        snap = draft.freeze(revision=1)
        with pytest.raises(InvariantError) as exc_info:
            assert_invariants(snap)
        err = cast(InvariantError, exc_info.value)
        assert err.revision == 1
        assert len(err.violations) > 0

    def test_focused_window_workspace_mismatch(self) -> None:
        win = Window(
            id=10,
            app_id="test",
            title="Test",
            workspace_id=2,
            is_focused=True,
            is_floating=False,
            is_urgent=False,
            pid=None,
            focus_timestamp=None,
            layout=_layout(),
        )
        draft = _make_valid_draft()
        draft.windows[10] = WindowState(window_id=10, protocol=win)
        snap = draft.freeze(revision=1)
        violations = collect_invariant_violations(snap)
        assert any("workspace_id" in v and "match" in v for v in violations)
