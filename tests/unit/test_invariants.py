from __future__ import annotations

from tests.factories.protocol import (
    make_keyboard_layouts,
    make_output,
    make_overview,
    make_window,
    make_workspace,
)

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.invariants import collect_invariant_violations
from niri_state.snapshot import Snapshot


def test_collects_missing_workspace_for_window() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={"HDMI-A-1": make_output()},
        workspaces={},
        windows={100: make_window(id=100, workspace_id=99)},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    violations = collect_invariant_violations(snapshot)
    assert any(v.code == "window_workspace_missing" for v in violations)


def test_workspace_without_output_is_allowed() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={1: make_workspace(id=1, output=None)},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    violations = collect_invariant_violations(snapshot)
    assert not any(v.code == "workspace_output_missing" for v in violations)
