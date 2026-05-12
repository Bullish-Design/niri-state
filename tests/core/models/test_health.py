from __future__ import annotations

import pytest

from niri_state._core.models.health import HealthState, validate_transition
from niri_state.errors import StateLifecycleError


class TestLifecycleFSM:
    @pytest.mark.parametrize(
        "current,target",
        [
            (HealthState.BOOTSTRAPPING, HealthState.LIVE),
            (HealthState.BOOTSTRAPPING, HealthState.FAILED),
            (HealthState.LIVE, HealthState.STALE),
            (HealthState.LIVE, HealthState.CLOSED),
            (HealthState.STALE, HealthState.RESYNCING),
            (HealthState.STALE, HealthState.LIVE),
            (HealthState.STALE, HealthState.CLOSED),
            (HealthState.RESYNCING, HealthState.LIVE),
            (HealthState.RESYNCING, HealthState.STALE),
            (HealthState.RESYNCING, HealthState.FAILED),
            (HealthState.RESYNCING, HealthState.CLOSED),
            (HealthState.FAILED, HealthState.CLOSED),
        ],
    )
    def test_legal_transitions_succeed(self, current: HealthState, target: HealthState) -> None:
        validate_transition(current, target, reason="test")

    @pytest.mark.parametrize(
        "current,target",
        [
            (HealthState.BOOTSTRAPPING, HealthState.STALE),
            (HealthState.BOOTSTRAPPING, HealthState.CLOSED),
            (HealthState.LIVE, HealthState.BOOTSTRAPPING),
            (HealthState.LIVE, HealthState.RESYNCING),
            (HealthState.LIVE, HealthState.FAILED),
            (HealthState.CLOSED, HealthState.LIVE),
            (HealthState.CLOSED, HealthState.BOOTSTRAPPING),
            (HealthState.FAILED, HealthState.LIVE),
            (HealthState.FAILED, HealthState.STALE),
        ],
    )
    def test_illegal_transitions_raise(self, current: HealthState, target: HealthState) -> None:
        with pytest.raises(StateLifecycleError) as exc_info:
            validate_transition(current, target, reason="test")
        exc = exc_info.value
        assert exc.current_state == current.value  # type: ignore[unresolved-attribute]
        assert exc.target_state == target.value  # type: ignore[unresolved-attribute]

    def test_transition_reason_in_error(self) -> None:
        with pytest.raises(StateLifecycleError, match="some reason"):
            validate_transition(HealthState.CLOSED, HealthState.LIVE, reason="some reason")
