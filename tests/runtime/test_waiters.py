from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from niri_pypc.types.generated.models import KeyboardLayouts

from niri_state._core.models.changes import ChangeSet
from niri_state._core.models.entities import KeyboardState, OverviewState
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import CompatibilityInfo, DiagnosticsInfo, NiriSnapshot
from niri_state._runtime.waiters import wait_for_selector, wait_until
from niri_state.config import NiriStateConfig
from niri_state.errors import WaitTimeoutError


def _make_minimal_snapshot(**overrides):
    defaults: dict[str, object] = dict(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_output_name=None,
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard=KeyboardState(
            protocol=KeyboardLayouts(current_idx=0, names=["us"]),
            current_name="us",
        ),
        overview=OverviewState(is_open=False),
        workspaces_by_output={},
        windows_by_workspace={},
        active_workspace_by_output={},
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(),
    )
    defaults.update(overrides)
    return NiriSnapshot(**defaults)


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

    async def subscribe(self) -> AsyncIterator[tuple[NiriSnapshot, ChangeSet | None]]:
        if self._current_snapshot is not None:
            yield (self._current_snapshot, None)

        try:
            while True:
                await self._publish_event.wait()
                if self._next_snapshot is not None:
                    yield (self._next_snapshot, None)
                    self._next_snapshot = None
                self._publish_event.clear()
                if self._closed:
                    break
        except asyncio.CancelledError:
            pass

    async def _publish(self, snap: NiriSnapshot, cs: ChangeSet | None) -> None:
        self._next_snapshot = snap
        self._publish_event.set()

    async def close(self) -> None:
        self._closed = True
        self._publish_event.set()


class TestWaitUntil:
    async def test_immediate_success(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot()
        state = MockNiriState(config, snap)

        result = await wait_until(state, lambda s: s.health == HealthState.LIVE)
        assert result.health == HealthState.LIVE

    async def test_wait_until_publishes(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot()
        state = MockNiriState(config, snap)

        async def publisher() -> None:
            await asyncio.sleep(0.02)
            new_snap = _make_minimal_snapshot(revision=2)
            await state._publish(new_snap, None)

        task = asyncio.create_task(publisher())
        result = await wait_until(state, lambda s: s.revision > 1, timeout=2.0)
        await task
        assert result.revision == 2

    async def test_timeout_raises(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot()
        state = MockNiriState(config, snap)

        with pytest.raises(WaitTimeoutError):
            await wait_until(state, lambda s: s.revision > 999, timeout=0.05)


class TestWatch:
    async def test_watch_emits_initial(self) -> None:
        pytest.skip("watch depends on async subscribe contract from NiriState")

    async def test_watch_only_on_change(self) -> None:
        pytest.skip("watch depends on async subscribe contract from NiriState")


class TestWaitForSelector:
    async def test_immediate_selector_match(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot()
        state = MockNiriState(config, snap)

        result = await wait_for_selector(state, lambda s: s.health, lambda h: h == HealthState.LIVE)
        assert result == HealthState.LIVE

    async def test_timeout_selector(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot()
        state = MockNiriState(config, snap)

        with pytest.raises(WaitTimeoutError):
            await wait_for_selector(state, lambda s: s.workspaces, lambda w: len(w) > 0, timeout=0.05)
