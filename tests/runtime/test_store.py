from __future__ import annotations

import pytest

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

        with pytest.raises(StopAsyncIteration):
            await sub_iter.__anext__()
