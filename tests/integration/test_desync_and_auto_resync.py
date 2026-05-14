from __future__ import annotations

import asyncio

import pytest

from niri_state.api.config import NiriStateConfig, ResyncPolicy
from niri_state.api.health import HealthState
from niri_state.api.state import NiriState
from tests.factories.bundle import FakeBundle, FakeClient
from tests.factories.events import make_window_urgency_changed_event


@pytest.mark.asyncio
async def test_auto_resync_requests_refresh() -> None:
    first = FakeBundle(
        events=(make_window_urgency_changed_event(id=999, urgent=True),),
        event_delay_s=0.05,
    )
    second = FakeBundle(client=FakeClient())
    bundles = [first, second]

    async def _open_bundle() -> FakeBundle:
        return bundles.pop(0)

    state = NiriState(config=NiriStateConfig(resync_policy=ResyncPolicy.AUTO), bundle_factory=_open_bundle)
    await state.connect()

    for _ in range(30):
        if state.snapshot.diagnostics.resync_count >= 1:
            break
        await asyncio.sleep(0.02)

    assert state.snapshot.health in {HealthState.LIVE, HealthState.STALE}
    assert state.snapshot.diagnostics.resync_count >= 1
    await state.close()
