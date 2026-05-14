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


def test_snapshot_empty_state() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.focused_output_name is None
    assert dict(snapshot.workspaces_by_output) == {}
    assert dict(snapshot.windows_by_workspace) == {}
    assert dict(snapshot.active_workspace_by_output) == {}


def test_snapshot_multiple_outputs() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={
            "HDMI-A-1": make_output(name="HDMI-A-1"),
            "DP-1": make_output(name="DP-1"),
        },
        workspaces={
            1: make_workspace(id=1, idx=1, output="HDMI-A-1", is_active=True, is_focused=True),
            2: make_workspace(id=2, idx=1, output="DP-1", is_active=True, is_focused=False),
        },
        windows={
            100: make_window(id=100, workspace_id=1),
            200: make_window(id=200, workspace_id=2),
        },
        focused_workspace_id=1,
        focused_window_id=100,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.workspaces_by_output["HDMI-A-1"] == (1,)
    assert snapshot.workspaces_by_output["DP-1"] == (2,)
    assert snapshot.windows_by_workspace[1] == (100,)
    assert snapshot.windows_by_workspace[2] == (200,)
    assert snapshot.focused_output_name == "HDMI-A-1"


def test_snapshot_keyboard_empty_names() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(names=[], current_idx=0),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.keyboard_current_name is None
