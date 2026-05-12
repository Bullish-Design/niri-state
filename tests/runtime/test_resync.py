from __future__ import annotations

import asyncio

from niri_state._core.models.health import HealthState
from niri_state._runtime.resync import ResyncCoordinator, create_resync_coordinator
from niri_state._runtime.store import NiriState
from niri_state.config import NiriStateConfig, ResyncPolicy
from tests._typing_helpers import make_minimal_snapshot


class TestResyncCoordinator:
    async def test_manual_mark_stale_no_auto_resync(self) -> None:
        config = NiriStateConfig(resync_policy=ResyncPolicy.MANUAL)
        state = NiriState(config)
        state._current_snapshot = make_minimal_snapshot(health=HealthState.LIVE)

        coordinator = ResyncCoordinator(state, config)
        coordinator.mark_stale("test reason")
        await asyncio.sleep(0)

        assert state.health == HealthState.STALE

    async def test_auto_mark_stale_triggers_resync(self) -> None:
        config = NiriStateConfig(resync_policy=ResyncPolicy.AUTO)
        state = NiriState(config)
        state._current_snapshot = make_minimal_snapshot(health=HealthState.LIVE)

        async def _fake_refresh() -> None:
            state._current_snapshot = make_minimal_snapshot(health=HealthState.LIVE, revision=2)

        state.refresh = _fake_refresh  # type: ignore[method-assign]

        coordinator = ResyncCoordinator(state, config)
        coordinator.mark_stale("test reason")
        assert coordinator._resync_task is not None
        await coordinator._resync_task

        assert state.health == HealthState.LIVE

    async def test_force_resync_available(self) -> None:
        config = NiriStateConfig(resync_policy=ResyncPolicy.MANUAL)
        state = NiriState(config)
        state._current_snapshot = make_minimal_snapshot(health=HealthState.LIVE)

        called = False

        async def _fake_refresh() -> None:
            nonlocal called
            called = True

        state.refresh = _fake_refresh  # type: ignore[method-assign]

        coordinator = ResyncCoordinator(state, config)
        await coordinator.force_resync()
        assert called

    async def test_create_resync_coordinator_factory(self) -> None:
        config = NiriStateConfig()
        state = NiriState(config)
        state._current_snapshot = make_minimal_snapshot()

        coordinator = create_resync_coordinator(state, config)
        assert isinstance(coordinator, ResyncCoordinator)
        assert coordinator.policy == config.resync_policy
