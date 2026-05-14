from __future__ import annotations

from tests.factories.protocol import (
    make_keyboard_layouts,
    make_output,
    make_overview,
    make_window,
    make_workspace,
)

from niri_state.api.health import HealthState
from niri_state.api.snapshot import Snapshot
from niri_state.core.diagnostics import Compatibility, Diagnostics


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


def test_snapshot_derived_indexes_are_stable() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={"HDMI-A-1": make_output()},
        workspaces={
            2: make_workspace(id=2, output="HDMI-A-1", idx=2),
            1: make_workspace(id=1, output="HDMI-A-1", idx=1),
        },
        windows={
            101: make_window(id=101, workspace_id=1),
            100: make_window(id=100, workspace_id=1),
        },
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.workspaces_by_output["HDMI-A-1"] == (1, 2)
    assert snapshot.windows_by_workspace[1] == (100, 101)
