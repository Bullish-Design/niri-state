from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from niri_state._core.models.changes import ChangeSet
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._runtime.waiters import wait_for_selector, wait_until, watch
from niri_state.config import NiriStateConfig, WaitHealthPolicy
from niri_state.errors import WaitTimeoutError
from tests._typing_helpers import make_minimal_snapshot


class MockNiriState:
    def __init__(self, config: NiriStateConfig, initial_snapshot: NiriSnapshot) -> None:
        self._config = config
        self._current_snapshot = initial_snapshot
        self._closed = False
        self._publish_event = asyncio.Event()
        self._next_snapshot: NiriSnapshot | None = None

    @property
    def snapshot(self) -> NiriSnapshot | None:
        return self._current_snapshot

    def subscribe(self) -> AsyncIterator[tuple[NiriSnapshot, ChangeSet | None]]:
        async def _iter() -> AsyncIterator[tuple[NiriSnapshot, ChangeSet | None]]:
            if self._current_snapshot is not None:
                yield (self._current_snapshot, None)

            while True:
                await self._publish_event.wait()
                if self._next_snapshot is not None:
                    yield (self._next_snapshot, None)
                    self._next_snapshot = None
                self._publish_event.clear()
                if self._closed:
                    break

        return _iter()

    async def _publish(self, snap: NiriSnapshot, cs: ChangeSet | None) -> None:
        self._next_snapshot = snap
        self._publish_event.set()

    async def close(self) -> None:
        self._closed = True
        self._publish_event.set()


class TestWaitUntil:
    async def test_immediate_success(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot()
        state = MockNiriState(config, snap)

        result = await wait_until(state, lambda s: s.health == HealthState.LIVE)
        assert result.health == HealthState.LIVE

    async def test_wait_until_publishes(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot()
        state = MockNiriState(config, snap)

        async def publisher() -> None:
            await asyncio.sleep(0.02)
            new_snap = make_minimal_snapshot(revision=2)
            await state._publish(new_snap, None)

        task = asyncio.create_task(publisher())
        result = await wait_until(state, lambda s: s.revision > 1, timeout=2.0)
        await task
        assert result.revision == 2

    async def test_timeout_raises(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot()
        state = MockNiriState(config, snap)

        with pytest.raises(WaitTimeoutError):
            await wait_until(state, lambda s: s.revision > 999, timeout=0.05)

    async def test_live_only_policy_ignores_stale_snapshot(self) -> None:
        config = NiriStateConfig(wait_health_policy=WaitHealthPolicy.LIVE_ONLY)
        stale = make_minimal_snapshot(health=HealthState.STALE)
        state = MockNiriState(config, stale)

        with pytest.raises(WaitTimeoutError):
            await wait_until(state, lambda s: s.health == HealthState.STALE, timeout=0.05)


class TestWatch:
    async def test_watch_emits_initial(self) -> None:
        config = NiriStateConfig()
        state = MockNiriState(config, make_minimal_snapshot(revision=1))
        stream = watch(state, lambda s: s.revision)

        first = await asyncio.wait_for(stream.__anext__(), timeout=0.1)
        assert first == 1

    async def test_watch_only_on_change(self) -> None:
        config = NiriStateConfig()
        state = MockNiriState(config, make_minimal_snapshot(revision=1))
        stream = watch(state, lambda s: s.health)

        first = await asyncio.wait_for(stream.__anext__(), timeout=0.1)
        assert first is HealthState.LIVE

        await state._publish(make_minimal_snapshot(revision=2, health=HealthState.LIVE), None)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(stream.__anext__(), timeout=0.05)


class TestWaitForSelector:
    async def test_immediate_selector_match(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot()
        state = MockNiriState(config, snap)

        result = await wait_for_selector(state, lambda s: s.health, lambda h: h == HealthState.LIVE)
        assert result == HealthState.LIVE

    async def test_timeout_selector(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot()
        state = MockNiriState(config, snap)

        with pytest.raises(WaitTimeoutError):
            await wait_for_selector(state, lambda s: s.workspaces, lambda w: len(w) > 0, timeout=0.05)
