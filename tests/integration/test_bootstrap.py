from __future__ import annotations

import pytest

from niri_state.api.config import NiriStateConfig
from niri_state.api.health import HealthState
from niri_state.core.bootstrap import run_bootstrap
from tests.factories.bundle import FakeBundle, FakeClient
from tests.factories.events import make_windows_changed_event
from tests.factories.protocol import make_window


@pytest.mark.asyncio
async def test_run_bootstrap_builds_live_or_stale_snapshot(fake_bundle) -> None:
    outcome = await run_bootstrap(fake_bundle, config=NiriStateConfig())

    assert outcome.initial_snapshot.health in {HealthState.LIVE, HealthState.STALE}
    assert outcome.initial_snapshot.revision == 1


@pytest.mark.asyncio
async def test_run_bootstrap_replays_buffered_events_before_revision_one() -> None:
    client = FakeClient(windows=[make_window(id=100)])
    event = make_windows_changed_event(windows=[make_window(id=200)])
    bundle = FakeBundle(client=client, events=(event,))

    outcome = await run_bootstrap(bundle, config=NiriStateConfig())

    assert outcome.initial_snapshot.revision == 1
    assert 200 in outcome.initial_snapshot.windows
