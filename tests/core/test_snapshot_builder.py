from __future__ import annotations

from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    WindowLayout,
    Workspace,
)

from niri_state._core.models.bootstrap_payload import BootstrapPayload
from niri_state._core.models.health import HealthState
from niri_state._core.snapshot_builder import build_initial_draft


def _layout() -> WindowLayout:
    return WindowLayout.model_validate(
        {"tile_size": [100, 50], "window_offset_in_tile": [0, 0], "window_size": [100, 50]}
    )


def _make_payload(
    *,
    outputs: dict[str, Output] | None = None,
    workspaces: list[Workspace] | None = None,
    windows: list[Window] | None = None,
    focused_output: Output | None = None,
    focused_window: Window | None = None,
    keyboard_layouts: KeyboardLayouts | None = None,
    overview: Overview | None = None,
    compositor_version: str | None = "test-version",
) -> BootstrapPayload:
    default_output = Output(
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
    return BootstrapPayload(
        outputs=outputs if outputs is not None else {"DP-1": default_output},
        workspaces=workspaces
        if workspaces is not None
        else [
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
        windows=windows if windows is not None else [],
        focused_output=focused_output if focused_output is not None else default_output,
        focused_window=focused_window,
        keyboard_layouts=(
            keyboard_layouts if keyboard_layouts is not None else KeyboardLayouts(current_idx=0, names=["us"])
        ),
        overview=overview if overview is not None else Overview(is_open=False),
        compositor_version=compositor_version,
    )


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
            layout=_layout(),
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
