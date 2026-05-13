from __future__ import annotations

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.snapshot import Snapshot
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_output,
    make_overview,
    make_workspace,
)


def test_snapshot_derives_focused_output_name() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={"HDMI-A-1": make_output()},
        workspaces={1: make_workspace(id=1, output="HDMI-A-1")},
        windows={},
        focused_workspace_id=1,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.focused_output_name == "HDMI-A-1"


def test_snapshot_derives_keyboard_current_name() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(names=["US", "DE"], current_idx=1),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.keyboard_current_name == "DE"
