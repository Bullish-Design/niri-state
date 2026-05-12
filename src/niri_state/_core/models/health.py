from __future__ import annotations

import enum

from niri_state.errors import StateLifecycleError


class HealthState(enum.Enum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"


_LEGAL_TRANSITIONS: dict[HealthState, frozenset[HealthState]] = {
    HealthState.BOOTSTRAPPING: frozenset({HealthState.LIVE, HealthState.FAILED}),
    HealthState.LIVE: frozenset({HealthState.STALE, HealthState.CLOSED}),
    HealthState.STALE: frozenset(
        {
            HealthState.RESYNCING,
            HealthState.LIVE,
            HealthState.CLOSED,
        }
    ),
    HealthState.RESYNCING: frozenset(
        {
            HealthState.LIVE,
            HealthState.STALE,
            HealthState.FAILED,
            HealthState.CLOSED,
        }
    ),
    HealthState.FAILED: frozenset({HealthState.CLOSED}),
    HealthState.CLOSED: frozenset(),
}


def validate_transition(
    current: HealthState,
    target: HealthState,
    *,
    reason: str,
) -> None:
    """Validate a lifecycle state transition.

    Raises StateLifecycleError if the transition is not legal.
    """
    legal = _LEGAL_TRANSITIONS.get(current, frozenset())
    if target not in legal:
        raise StateLifecycleError(
            f"Illegal transition {current.value} -> {target.value}: {reason}",
            current_state=current.value,
            target_state=target.value,
        )
