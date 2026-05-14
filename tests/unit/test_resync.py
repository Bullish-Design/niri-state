from __future__ import annotations

import asyncio

import pytest

from niri_state.api.changes import ChangeCause
from niri_state.api.config import NiriStateConfig, ResyncPolicy
from niri_state.core.resync import ResyncCoordinator


class _DummyState:
    def __init__(self) -> None:
        self.refresh_count = 0
        self.failures_remaining = 0
        self.causes: list[ChangeCause] = []

    async def refresh(self, *, cause: ChangeCause = ChangeCause.REFRESH):
        self.refresh_count += 1
        self.causes.append(cause)
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise RuntimeError("refresh failed")


async def _wait_for_attempts(state: _DummyState, expected: int) -> None:
    for _ in range(200):
        if state.refresh_count >= expected:
            return
        await asyncio.sleep(0.001)
    raise AssertionError(f"timed out waiting for {expected} refresh attempts")


@pytest.mark.asyncio
async def test_resync_request_is_safe() -> None:
    state = _DummyState()
    coordinator = ResyncCoordinator(
        state,
        NiriStateConfig(resync_policy=ResyncPolicy.MANUAL),
    )
    coordinator.request()
    await coordinator.close()


@pytest.mark.asyncio
async def test_auto_resync_stops_after_max_attempts() -> None:
    state = _DummyState()
    state.failures_remaining = 10
    coordinator = ResyncCoordinator(
        state,
        NiriStateConfig(
            resync_policy=ResyncPolicy.AUTO,
            resync_max_attempts=3,
            resync_backoff_base=0.001,
        ),
    )
    await coordinator.start()
    coordinator.request()
    await _wait_for_attempts(state, 3)
    await coordinator.close()

    assert state.refresh_count == 3
    assert all(cause is ChangeCause.RESYNC for cause in state.causes)


@pytest.mark.asyncio
async def test_auto_resync_retries_then_succeeds() -> None:
    state = _DummyState()
    state.failures_remaining = 1
    coordinator = ResyncCoordinator(
        state,
        NiriStateConfig(
            resync_policy=ResyncPolicy.AUTO,
            resync_max_attempts=4,
            resync_backoff_base=0.001,
        ),
    )
    await coordinator.start()
    coordinator.request()
    await _wait_for_attempts(state, 2)
    await coordinator.close()

    assert state.refresh_count == 2
    assert all(cause is ChangeCause.RESYNC for cause in state.causes)


@pytest.mark.asyncio
async def test_auto_resync_uses_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _DummyState()
    state.failures_remaining = 3
    delays: list[float] = []
    real_sleep = asyncio.sleep

    async def _sleep(delay: float) -> None:
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr("niri_state.core.resync.asyncio.sleep", _sleep)

    coordinator = ResyncCoordinator(
        state,
        NiriStateConfig(
            resync_policy=ResyncPolicy.AUTO,
            resync_max_attempts=4,
            resync_backoff_base=0.5,
        ),
    )
    await coordinator.start()
    coordinator.request()
    await _wait_for_attempts(state, 4)
    await coordinator.close()

    coordinator_delays = [delay for delay in delays if delay >= 0.5]
    assert coordinator_delays == [0.5, 1.0, 2.0]
