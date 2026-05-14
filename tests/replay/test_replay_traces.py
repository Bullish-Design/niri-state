from __future__ import annotations

import pytest
from tests.factories.events import make_event_sequence
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_output,
    make_overview,
    make_workspace,
)

from niri_state.api.config import NiriStateConfig
from niri_state.api.health import HealthState
from niri_state.core.engine_state import EngineState
from niri_state.core.invariants import collect_invariant_violations
from niri_state.core.reconcile import reconcile
from niri_state.core.reducers import reduce_event


@pytest.mark.asyncio
async def test_replay_trace_converges() -> None:
    config = NiriStateConfig()
    engine = EngineState.empty()
    engine.health = HealthState.LIVE
    engine.outputs = {"HDMI-A-1": make_output()}
    engine.workspaces = {1: make_workspace(id=1, output="HDMI-A-1")}
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()

    revision = 0
    snapshot = engine.freeze(revision=revision)
    for event in make_event_sequence():
        result = reduce_event(
            engine,
            event,
            config=config,
            revision=revision,
        )
        if not result.applied:
            continue
        reconcile(engine)
        revision += 1
        snapshot = engine.freeze(revision=revision)
        assert collect_invariant_violations(snapshot) == ()

    assert set(snapshot.workspaces.keys()) == {1}
    assert set(snapshot.windows.keys()) == {100}
    assert snapshot.workspaces_by_output["HDMI-A-1"] == (1,)
    assert snapshot.windows_by_workspace[1] == (100,)
    assert snapshot.health in {HealthState.LIVE, HealthState.STALE}
