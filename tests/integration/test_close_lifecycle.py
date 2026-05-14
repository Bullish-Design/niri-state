from __future__ import annotations

import pytest

from niri_state.api.health import HealthState
from niri_state.api.state import NiriState


@pytest.mark.asyncio
async def test_close_transitions_state(fake_runtime_bundle) -> None:
    state = NiriState()

    async def _open_bundle():
        return fake_runtime_bundle

    state._open_bundle = _open_bundle  # type: ignore[method-assign]
    await state.connect()
    await state.close()

    assert state.snapshot.health is HealthState.CLOSED


@pytest.mark.asyncio
async def test_context_manager_opens_and_closes(fake_runtime_bundle) -> None:
    state = NiriState()

    async def _open_bundle():
        return fake_runtime_bundle

    state._open_bundle = _open_bundle  # type: ignore[method-assign]

    async with state:
        assert state.snapshot is not None
        assert state.health() in {HealthState.LIVE, HealthState.STALE}

    assert state.snapshot.health is HealthState.CLOSED
