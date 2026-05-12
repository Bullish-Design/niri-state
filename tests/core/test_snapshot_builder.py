from __future__ import annotations

from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    Workspace,
)

from niri_state._core.models.bootstrap_payload import BootstrapPayload
from niri_state._core.models.health import HealthState
from niri_state._core.snapshot_builder import build_initial_draft


def _make_payload(**overrides) -> BootstrapPayload:
    defaults = {
        "outputs": {
            "DP-1": Output(
                name="DP-1",
                make="Test",
                model="Test",
                serial=None,
                physical_size=None,
                modes=[],
                current_mode=None,
                is_custom_mode=False,
                logical=None,
                vrr_supported=False,
                vrr_enabled=False,
            )
        },
        "workspaces": [
            Workspace(
                id=1,
                idx=0,
                name="1",
                output="DP-1",
                is_active=True,
                is_focused=True,
                is_urgent=False,
                active_window_id=None,
            )
        ],
        "windows": [],
        "focused_output": Output(
            name="DP-1",
            make="Test",
            model="Test",
            serial=None,
            physical_size=None,
            modes=[],
            current_mode=None,
            is_custom_mode=False,
            logical=None,
            vrr_supported=False,
            vrr_enabled=False,
        ),
        "focused_window": None,
        "keyboard_layouts": KeyboardLayouts(current_idx=0, names=["us"]),
        "overview": Overview(is_open=False),
        "compositor_version": "test-version",
    }
    defaults.update(overrides)
    return BootstrapPayload(**defaults)


class TestSnapshotBuilder:
    def test_build_initial_draft_outputs(self) -> None:
        payload = _make_payload()
        draft = build_initial_draft(payload)
        assert "DP-1" in draft.outputs
        assert draft.outputs["DP-1"].output_name == "DP-1"

    def test_build_initial_draft_workspaces(self) -> None:
        payload = _make_payload()
        draft = build_initial_draft(payload)
        assert 1 in draft.workspaces
        assert draft.workspaces[1].workspace_id == 1

    def test_build_initial_draft_focus_from_focused_window(self) -> None:
        win = Window(
            id=5,
            app_id="test",
            title="Test",
            workspace_id=1,
            is_focused=True,
            is_floating=False,
            is_urgent=False,
            pid=None,
            focus_timestamp=None,
            layout={"tile_size": [100, 50], "window_offset_in_tile": [0, 0], "window_size": [100, 50]},
        )
        payload = _make_payload(
            windows=[win],
            focused_window=win,
        )
        draft = build_initial_draft(payload)
        assert draft.focused_window_id == 5
        assert draft.focused_workspace_id == 1

    def test_build_initial_draft_focus_fallback_from_focused_workspace(self) -> None:
        payload = _make_payload()
        draft = build_initial_draft(payload)
        assert draft.focused_workspace_id == 1
        assert draft.focused_output_name == "DP-1"

    def test_keyboard_current_name_in_bounds(self) -> None:
        payload = _make_payload(keyboard_layouts=KeyboardLayouts(current_idx=0, names=["us", "de"]))
        draft = build_initial_draft(payload)
        assert draft.keyboard.current_name == "us"

    def test_keyboard_current_name_out_of_bounds(self) -> None:
        payload = _make_payload(keyboard_layouts=KeyboardLayouts(current_idx=5, names=["us", "de"]))
        draft = build_initial_draft(payload)
        assert draft.keyboard.current_name is None

    def test_compatibility_info_carries_version(self) -> None:
        payload = _make_payload(compositor_version="1.2.3")
        draft = build_initial_draft(payload)
        assert draft.compatibility.compositor_version == "1.2.3"

    def test_initial_health_is_bootstrapping(self) -> None:
        payload = _make_payload()
        draft = build_initial_draft(payload)
        assert draft.health is HealthState.BOOTSTRAPPING
