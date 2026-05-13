from __future__ import annotations

import pytest

from niri_state.bootstrap import run_bootstrap
from niri_state.config import NiriStateConfig
from niri_state.health import HealthState


@pytest.mark.asyncio
async def test_run_bootstrap_builds_live_or_stale_snapshot(fake_bundle) -> None:
    outcome = await run_bootstrap(fake_bundle, config=NiriStateConfig())

    assert outcome.initial_snapshot.health in {HealthState.LIVE, HealthState.STALE}
    assert outcome.initial_snapshot.revision == 1
