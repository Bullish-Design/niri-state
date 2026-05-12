from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

    layouts_dict = trace.keyboard_layouts
    layouts = KeyboardLayouts(**layouts_dict)

    outputs = {}
    for name, out_dict in trace.outputs.items():
        outputs[name] = Output(**out_dict)

    workspaces = [Workspace(**ws) for ws in trace.workspaces]

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
        windows.append(WindowModel(**w))

    focused_output: Output | None = None
    if trace.focused_output and trace.focused_output in outputs:
        focused_output = outputs[trace.focused_output]

    focused_window: WindowModel | None = None
    for w in windows:
        if w.id == trace.focused_window_id:
            focused_window = w
            break

    overview = OverviewModel(**trace.overview)

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
