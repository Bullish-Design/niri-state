from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from niri_state._core.models.health import HealthState


@dataclass(frozen=True)
class ReplayTrace:
    name: str
    outputs: dict[str, Any]
    workspaces: list[Any]
    windows: list[dict[str, Any]]
    focused_output: str | None
    focused_window_id: int | None
    keyboard_layouts: dict[str, Any]
    overview: dict[str, Any]
    events: tuple[Any, ...]
    expected_workspace_ids: tuple[int, ...]
    expected_window_ids: tuple[int, ...]
    expected_health: HealthState
    policy: str = "stale"


def replay_trace(trace: ReplayTrace) -> tuple[Any, tuple[str, ...], HealthState]:
    from niri_pypc.types.generated.models import KeyboardLayouts, Output, Workspace
    from niri_pypc.types.generated.models import Overview as OverviewModel
    from niri_pypc.types.generated.models import Window as WindowModel

    from niri_state._core.invariants import collect_invariant_violations
    from niri_state._core.models.bootstrap_payload import BootstrapPayload
    from niri_state._core.reducers.root import reduce_event
    from niri_state._core.snapshot_builder import build_initial_draft

    layouts = KeyboardLayouts.model_validate(trace.keyboard_layouts)

    outputs: dict[str, Output] = {}
    for name, out_dict in trace.outputs.items():
        outputs[name] = Output.model_validate(out_dict)

    workspaces = [Workspace.model_validate(ws) for ws in trace.workspaces]

    windows = []
    for win_dict in trace.windows:
        w = dict(win_dict)
        if "layout" not in w:
            w["layout"] = {
                "pos_in_scrolling_layout": None,
                "tile_pos_in_workspace_view": None,
                "tile_size": [],
                "window_offset_in_tile": [],
                "window_size": [],
                "position": None,
                "size": None,
            }
        windows.append(WindowModel.model_validate(w))

    focused_output: Output | None = None
    if trace.focused_output and trace.focused_output in outputs:
        focused_output = outputs[trace.focused_output]

    focused_window: WindowModel | None = None
    for w in windows:
        if w.id == trace.focused_window_id:
            focused_window = w
            break

    overview = OverviewModel.model_validate(trace.overview)

    payload = BootstrapPayload(
        outputs=outputs,
        workspaces=workspaces,
        windows=windows,
        focused_output=focused_output,
        focused_window=focused_window,
        keyboard_layouts=layouts,
        overview=overview,
        compositor_version=None,
    )

    draft = build_initial_draft(payload)

    for event in trace.events:
        reduce_event(draft, event, trace.policy)

    final_snapshot = draft.freeze(revision=len(trace.events) + 1, force_health=HealthState.LIVE)

    violations = collect_invariant_violations(final_snapshot)
    violation_msgs = tuple(v.message for v in violations)

    return final_snapshot, violation_msgs, final_snapshot.health


def replay_trace_deterministic(trace: ReplayTrace) -> bool:
    snap1, _, _ = replay_trace(trace)
    snap2, _, _ = replay_trace(trace)

    def projection(s: Any) -> tuple[Any, ...]:
        return (
            s.revision,
            tuple(sorted(s.windows.keys())),
            tuple(sorted(s.workspaces.keys())),
            s.health,
        )

    return projection(snap1) == projection(snap2)


def _layout_dict():
    return {
        "pos_in_scrolling_layout": None,
        "tile_pos_in_workspace_view": None,
        "tile_size": [],
        "window_offset_in_tile": [],
        "window_size": [],
        "position": None,
        "size": None,
    }


class TestReplayTraces:
    def test_replace_all_event_sequence(self) -> None:
        from niri_pypc.types.generated.event import WindowsChangedEvent
        from niri_pypc.types.generated.models import Window

        trace = ReplayTrace(
            name="replace-all+incremental",
            outputs={
                "DP-1": {
                    "name": "DP-1",
                    "make": "Dell",
                    "model": "U2720Q",
                    "is_custom_mode": False,
                    "modes": [],
                    "vrr_supported": False,
                    "vrr_enabled": False,
                },
            },
            workspaces=[
                {
                    "id": 1,
                    "idx": 0,
                    "name": "main",
                    "output": "DP-1",
                    "is_active": True,
                    "is_focused": True,
                    "is_urgent": False,
                    "active_window_id": None,
                },
            ],
            windows=[],
            focused_output="DP-1",
            focused_window_id=None,
            keyboard_layouts={"current_idx": 0, "names": ["us"]},
            overview={"is_open": False},
            events=(
                WindowsChangedEvent(
                    windows=[
                        Window(
                            id=100,
                            app_id="kitty",
                            title="Terminal",
                            workspace_id=1,
                            is_focused=True,
                            is_floating=False,
                            is_urgent=False,
                            pid=1234,
                            focus_timestamp=None,
                            layout=_layout_dict(),
                        ),
                        Window(
                            id=101,
                            app_id="firefox",
                            title="Browser",
                            workspace_id=1,
                            is_focused=False,
                            is_floating=False,
                            is_urgent=False,
                            pid=5678,
                            focus_timestamp=None,
                            layout=_layout_dict(),
                        ),
                    ]
                ),
            ),
            expected_workspace_ids=(1,),
            expected_window_ids=(100, 101),
            expected_health=HealthState.LIVE,
        )

        snap, violations, health = replay_trace(trace)
        assert health == HealthState.LIVE
        assert snap.revision == 2
        assert 100 in snap.windows
        assert 101 in snap.windows
        assert len(violations) == 0

    def test_replay_determinism(self) -> None:
        trace = ReplayTrace(
            name="determinism-check",
            outputs={},
            workspaces=[],
            windows=[],
            focused_output=None,
            focused_window_id=None,
            keyboard_layouts={"current_idx": 0, "names": ["us"]},
            overview={"is_open": False},
            events=(),
            expected_workspace_ids=(),
            expected_window_ids=(),
            expected_health=HealthState.LIVE,
        )

        assert replay_trace_deterministic(trace)

    def test_unknown_event_stale_policy_trace(self) -> None:
        from niri_pypc.types.generated.event import UnknownEvent

        trace = ReplayTrace(
            name="unknown-event-stale",
            outputs={},
            workspaces=[],
            windows=[],
            focused_output=None,
            focused_window_id=None,
            keyboard_layouts={"current_idx": 0, "names": ["us"]},
            overview={"is_open": False},
            events=(UnknownEvent(variant_name="SomeUnknownEvent", raw_payload={}),),
            expected_workspace_ids=(),
            expected_window_ids=(),
            expected_health=HealthState.LIVE,
        )

        snap, violations, health = replay_trace(trace)
        assert health == HealthState.LIVE
        assert snap.diagnostics.unknown_events_seen == 1

    def test_floating_window_persistence_trace(self) -> None:
        trace = ReplayTrace(
            name="floating-window-persistence",
            outputs={
                "DP-1": {
                    "name": "DP-1",
                    "make": "Dell",
                    "model": "U2720Q",
                    "is_custom_mode": False,
                    "modes": [],
                    "vrr_supported": False,
                    "vrr_enabled": False,
                },
            },
            workspaces=[
                {
                    "id": 1,
                    "idx": 0,
                    "name": "main",
                    "output": "DP-1",
                    "is_active": True,
                    "is_focused": True,
                    "is_urgent": False,
                    "active_window_id": None,
                },
            ],
            windows=[
                {
                    "id": 200,
                    "app_id": "floating",
                    "title": "Floating",
                    "workspace_id": None,
                    "is_focused": False,
                    "is_floating": True,
                    "is_urgent": False,
                    "pid": 9999,
                    "focus_timestamp": None,
                    "layout": _layout_dict(),
                },
            ],
            focused_output="DP-1",
            focused_window_id=None,
            keyboard_layouts={"current_idx": 0, "names": ["us"]},
            overview={"is_open": False},
            events=(),
            expected_workspace_ids=(1,),
            expected_window_ids=(200,),
            expected_health=HealthState.LIVE,
        )

        snap, violations, health = replay_trace(trace)
        assert health == HealthState.LIVE
        assert 200 in snap.windows
        assert snap.windows[200].protocol.workspace_id is None

    def test_unknown_event_fail_policy_trace(self) -> None:
        from niri_pypc.types.generated.event import UnknownEvent

        trace = ReplayTrace(
            name="unknown-event-fail",
            outputs={},
            workspaces=[],
            windows=[],
            focused_output=None,
            focused_window_id=None,
            keyboard_layouts={"current_idx": 0, "names": ["us"]},
            overview={"is_open": False},
            events=(UnknownEvent(variant_name="SomeUnknownEvent", raw_payload={}),),
            expected_workspace_ids=(),
            expected_window_ids=(),
            expected_health=HealthState.FAILED,
            policy="fail",
        )

        from niri_state.errors import DesyncError

        with pytest.raises(DesyncError):
            replay_trace(trace)

    def test_multi_output_active_workspace_trace(self) -> None:
        from niri_pypc.types.generated.event import WorkspaceActivatedEvent

        trace = ReplayTrace(
            name="multi-output-active-workspace",
            outputs={
                "DP-1": {
                    "name": "DP-1",
                    "make": "Dell",
                    "model": "U2720Q",
                    "is_custom_mode": False,
                    "modes": [],
                    "vrr_supported": False,
                    "vrr_enabled": False,
                },
                "HDMI-1": {
                    "name": "HDMI-1",
                    "make": "Samsung",
                    "model": "SyncMaster",
                    "is_custom_mode": False,
                    "modes": [],
                    "vrr_supported": False,
                    "vrr_enabled": False,
                },
            },
            workspaces=[
                {
                    "id": 1,
                    "idx": 0,
                    "name": "main",
                    "output": "DP-1",
                    "is_active": True,
                    "is_focused": True,
                    "is_urgent": False,
                    "active_window_id": None,
                },
                {
                    "id": 2,
                    "idx": 1,
                    "name": "secondary",
                    "output": "HDMI-1",
                    "is_active": False,
                    "is_focused": False,
                    "is_urgent": False,
                    "active_window_id": None,
                },
            ],
            windows=[],
            focused_output="DP-1",
            focused_window_id=None,
            keyboard_layouts={"current_idx": 0, "names": ["us"]},
            overview={"is_open": False},
            events=(
                WorkspaceActivatedEvent(
                    id=2,
                    focused=False,
                ),
            ),
            expected_workspace_ids=(1, 2),
            expected_window_ids=(),
            expected_health=HealthState.LIVE,
            policy="stale",
        )

        snap, violations, health = replay_trace(trace)
        assert health == HealthState.LIVE
        assert 1 in snap.workspaces
        assert 2 in snap.workspaces
        assert snap.workspaces[1].protocol.is_active is True
        assert snap.workspaces[2].protocol.is_active is True


class TestBootstrapConvergence:
    async def test_bootstrap_snapshot_has_health_live(self) -> None:
        pytest.skip("integration test requires live socket")

    async def test_replay_determinism_convergence(self) -> None:
        pytest.skip("integration test requires live socket")

    async def test_workspace_window_consistency(self) -> None:
        pytest.skip("integration test requires live socket")
