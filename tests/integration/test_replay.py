from __future__ import annotations

from dataclasses import dataclass

from niri_state._core.models.health import HealthState


@dataclass(frozen=True)
class ReplayTrace:
    """A complete replay trace for deterministic testing."""

    name: str
    outputs: dict[str, object]
    workspaces: list[object]
    windows: list[object]
    focused_output: object | None
    focused_window: object | None
    keyboard_layouts: object
    overview: object
    events: tuple[object, ...]
    expected_workspace_ids: tuple[int, ...]
    expected_window_ids: tuple[int, ...]
    expected_health: HealthState


def replay_trace(
    trace: ReplayTrace,
) -> tuple[object, tuple[str, ...]]:
    """Replay a trace and return final snapshot + violations.

    Returns (final_snapshot, invariant_violations).
    """
    from niri_state._core.models.bootstrap_payload import BootstrapPayload
    from niri_state._core.snapshot_builder import build_initial_draft
    from niri_state._core.invariants import collect_invariant_violations
    from niri_state._core.reducers.root import reduce_event

    payload = BootstrapPayload(
        outputs={},  # type: ignore[arg-type]
        workspaces=[],  # type: ignore[arg-type]
        windows=[],  # type: ignore[arg-type]
        focused_output=None,
        focused_window=None,
        keyboard_layouts=trace.keyboard_layouts,
        overview=trace.overview,
    )

    draft = build_initial_draft(payload)

    for event in trace.events:
        reduce_event(draft, event, "stale")

    final_snapshot = draft.freeze(revision=len(trace.events))
    violations = collect_invariant_violations(final_snapshot)

    return final_snapshot, violations
