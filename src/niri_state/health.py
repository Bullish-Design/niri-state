from __future__ import annotations

from enum import StrEnum

from niri_state.errors import StateLifecycleError


class HealthState(StrEnum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"


_ALLOWED_TRANSITIONS: dict[HealthState, frozenset[HealthState]] = {
    HealthState.BOOTSTRAPPING: frozenset(
        {
            HealthState.LIVE,
            HealthState.STALE,
            HealthState.CLOSED,
            HealthState.FAILED,
        }
    ),
    HealthState.LIVE: frozenset(
        {
            HealthState.STALE,
            HealthState.RESYNCING,
            HealthState.CLOSED,
            HealthState.FAILED,
        }
    ),
    HealthState.STALE: frozenset(
        {
            HealthState.RESYNCING,
            HealthState.LIVE,
            HealthState.CLOSED,
            HealthState.FAILED,
        }
    ),
    HealthState.RESYNCING: frozenset(
        {
            HealthState.LIVE,
            HealthState.STALE,
            HealthState.CLOSED,
            HealthState.FAILED,
        }
    ),
    HealthState.CLOSED: frozenset(),
    HealthState.FAILED: frozenset(),
}


def validate_transition(current: HealthState, target: HealthState) -> None:
    if current == target:
        return

    allowed = _ALLOWED_TRANSITIONS[current]
    if target not in allowed:
        raise StateLifecycleError(
            f"invalid health transition: {current!s} -> {target!s}",
            current_state=current,
            target_state=target,
            operation="health_transition",
        )
