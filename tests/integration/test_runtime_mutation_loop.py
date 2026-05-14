from __future__ import annotations

import asyncio

import pytest

from niri_state.api.state import NiriState
from tests.factories.bundle import FakeBundle
from tests.factories.events import make_windows_changed_event
from tests.factories.protocol import make_window


@pytest.mark.asyncio
async def test_runtime_publishes_after_event() -> None:
    event = make_windows_changed_event(windows=[make_window(id=999)])
    fake_runtime_bundle = FakeBundle(events=(event,))

    async def _open_bundle() -> FakeBundle:
        return fake_runtime_bundle

    state = NiriState(bundle_factory=_open_bundle)
    await state.connect()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert state.snapshot.revision >= 2
    assert 999 in state.snapshot.windows

    await state.close()


@pytest.mark.asyncio
async def test_mutation_loop_marks_stale_on_desync() -> None:
    from niri_state.api.health import HealthState
    from tests.factories.events import make_window_urgency_changed_event

    event = make_window_urgency_changed_event(id=999, urgent=True)
    bundle = FakeBundle(events=(event,), event_delay_s=0.01)

    async def _open_bundle() -> FakeBundle:
        return bundle

    state = NiriState(bundle_factory=_open_bundle)
    await state.connect()

    for _ in range(20):
        if state.snapshot.health is HealthState.STALE:
            break
        await asyncio.sleep(0.02)

    assert state.snapshot.health is HealthState.STALE
    assert state.snapshot.diagnostics.desynced is True
    await state.close()
