from __future__ import annotations

import pytest

from niri_state.config import NiriStateConfig, ResyncPolicy
from niri_state.resync import ResyncCoordinator


class _DummyState:
    def __init__(self) -> None:
        self.refresh_count = 0

    async def refresh(self):
        self.refresh_count += 1


@pytest.mark.asyncio
async def test_resync_request_is_safe() -> None:
    state = _DummyState()
    coordinator = ResyncCoordinator(
        state,
        NiriStateConfig(resync_policy=ResyncPolicy.MANUAL),
    )
    coordinator.request()
    await coordinator.close()
