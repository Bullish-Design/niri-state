from __future__ import annotations

import pytest

from niri_state.api.errors import StateLifecycleError
from niri_state.api.health import HealthState, validate_transition


def test_validate_transition_allows_live_to_stale() -> None:
    validate_transition(HealthState.LIVE, HealthState.STALE)


def test_validate_transition_rejects_closed_to_live() -> None:
    with pytest.raises(StateLifecycleError):
        validate_transition(HealthState.CLOSED, HealthState.LIVE)
