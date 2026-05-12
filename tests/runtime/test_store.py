from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from niri_state._core.models.changes import ChangeCause, ChangeSet
from niri_state._core.models.health import HealthState
from niri_state._runtime.store import NiriState
from niri_state.config import NiriStateConfig
from tests._typing_helpers import make_minimal_snapshot


class TestNiriStateStore:
    async def test_revision_monotonicity(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot(revision=5)
        state = NiriState(config)
        state._current_snapshot = snap
        state._revision = 5

        assert state.health == HealthState.LIVE

    async def test_subscribe_returns_iterator(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot()
        state = NiriState(config)
        state._current_snapshot = snap

        sub = state.subscribe()
        assert hasattr(sub, "__aiter__")
        snap, changeset = await asyncio.wait_for(sub.__anext__(), timeout=0.5)
        assert snap.revision == 1
        assert changeset is None

    async def test_subscribe_multiple(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot()
        state = NiriState(config)
        state._current_snapshot = snap

        sub1 = state.subscribe()
        sub2 = state.subscribe()

        assert sub1 is not None
        assert sub2 is not None

    async def test_idempotent_close(self) -> None:
        config = NiriStateConfig()
        state = NiriState(config)
        snap = make_minimal_snapshot()
        state._current_snapshot = snap

        await state.close()
        await state.close()

    async def test_close_cancels_subscribers(self) -> None:
        config = NiriStateConfig()
        snap = make_minimal_snapshot()
        state = NiriState(config)
        state._current_snapshot = snap

        sub_iter = state.subscribe()
        await state.close()
        snap, _ = await asyncio.wait_for(sub_iter.__anext__(), timeout=0.5)
        assert snap.revision == 1

        with pytest.raises(StopAsyncIteration):
            await sub_iter.__anext__()

    async def test_refresh_preserves_monotonic_revision(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = NiriState(NiriStateConfig())
        state._current_snapshot = make_minimal_snapshot(revision=5, health=HealthState.LIVE)
        state._revision = 5

        async def _close() -> None:
            return None

        async def _next(*, timeout: float | None = None) -> object:
            raise TimeoutError

        idle_bundle = SimpleNamespace(close=_close, events=SimpleNamespace(next=_next))
        state._bundle = cast(Any, idle_bundle)
        state._mutation_task = asyncio.create_task(asyncio.sleep(60))

        bootstrap_snapshot = make_minimal_snapshot(revision=1, health=HealthState.LIVE)
        bootstrap_changeset = ChangeSet(
            revision=1,
            timestamp=bootstrap_snapshot.timestamp,
            cause=ChangeCause.BOOTSTRAP,
            changed_domains=frozenset(),
        )

        async def _fake_run_bootstrap(config: NiriStateConfig) -> object:
            return SimpleNamespace(
                bundle=idle_bundle,
                initial_snapshot=bootstrap_snapshot,
                initial_changeset=bootstrap_changeset,
            )

        monkeypatch.setattr("niri_state._runtime.bootstrap.run_bootstrap", _fake_run_bootstrap)
        await state.refresh()
        snapshot = state.snapshot
        assert snapshot is not None
        assert snapshot.revision > 5

        await state.close()

    async def test_start_bootstraps_and_connects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        snapshot = make_minimal_snapshot(revision=3, health=HealthState.LIVE)

        async def _close() -> None:
            return None

        async def _next(*, timeout: float | None = None) -> object:
            raise TimeoutError

        bundle = SimpleNamespace(close=_close, events=SimpleNamespace(next=_next))
        outcome = SimpleNamespace(
            bundle=bundle,
            initial_snapshot=snapshot,
            initial_changeset=ChangeSet(
                revision=3,
                timestamp=snapshot.timestamp,
                cause=ChangeCause.BOOTSTRAP,
                changed_domains=frozenset(),
            ),
        )

        async def _fake_run_bootstrap(config: NiriStateConfig) -> object:
            return outcome

        monkeypatch.setattr("niri_state._runtime.bootstrap.run_bootstrap", _fake_run_bootstrap)
        state = await NiriState.start(NiriStateConfig())
        assert state.snapshot is not None
        assert state.snapshot.revision == 3
        await state.close()
