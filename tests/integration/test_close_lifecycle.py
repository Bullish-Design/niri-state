from __future__ import annotations

import pytest

from niri_state.api.health import HealthState
from niri_state.api.state import NiriState


@pytest.mark.asyncio
async def test_close_transitions_state(fake_runtime_bundle) -> None:
    async def _open_bundle():
        return fake_runtime_bundle

    state = NiriState(bundle_factory=_open_bundle)
    await state.connect()
    await state.close()

    assert state.snapshot.health is HealthState.CLOSED


@pytest.mark.asyncio
async def test_context_manager_opens_and_closes(fake_runtime_bundle) -> None:
    async def _open_bundle():
        return fake_runtime_bundle

    state = NiriState(bundle_factory=_open_bundle)

    async with state:
        assert state.snapshot is not None
        assert state.health() in {HealthState.LIVE, HealthState.STALE}

    assert state.snapshot.health is HealthState.CLOSED


@pytest.mark.asyncio
async def test_connect_when_already_started_raises() -> None:
    from tests.factories.bundle import FakeBundle
    from niri_state.api.errors import StateLifecycleError

    bundle = FakeBundle()

    async def _open_bundle():
        return bundle

    state = NiriState(bundle_factory=_open_bundle)
    await state.connect()

    with pytest.raises(StateLifecycleError, match="already started"):
        await state.connect()

    await state.close()


@pytest.mark.asyncio
async def test_connect_when_already_closed_raises() -> None:
    from tests.factories.bundle import FakeBundle
    from niri_state.api.errors import StateLifecycleError

    bundle = FakeBundle()

    async def _open_bundle():
        return bundle

    state = NiriState(bundle_factory=_open_bundle)
    await state.connect()
    await state.close()

    with pytest.raises(StateLifecycleError, match="already closed"):
        await state.connect()


@pytest.mark.asyncio
async def test_refresh_when_not_connected_raises() -> None:
    from niri_state.api.errors import StateLifecycleError

    state = NiriState()

    with pytest.raises(StateLifecycleError, match="not connected"):
        await state.refresh()


@pytest.mark.asyncio
async def test_subscriber_receives_closed_on_close(fake_runtime_bundle) -> None:
    async def _open_bundle():
        return fake_runtime_bundle

    state = NiriState(bundle_factory=_open_bundle)
    await state.connect()

    sub = state.subscribe()

    initial = await sub.__anext__()
    assert initial.snapshot.health is HealthState.LIVE

    await state.close()

    items_after_close = [item async for item in sub]
    assert items_after_close == []
