from __future__ import annotations

import asyncio

import pytest

from niri_state.store import NiriState
from tests.factories.bundle import FakeBundle
from tests.factories.events import make_windows_changed_event
from tests.factories.protocol import make_window


@pytest.mark.asyncio
async def test_runtime_publishes_after_event() -> None:
    event = make_windows_changed_event(windows=[make_window(id=999)])
    fake_runtime_bundle = FakeBundle(events=(event,))
    state = NiriState()

    async def _open_bundle() -> FakeBundle:
        return fake_runtime_bundle

    state._open_bundle = _open_bundle  # type: ignore[method-assign]
    await state.connect()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert state.snapshot.revision >= 2
    assert 999 in state.snapshot.windows

    await state.close()
