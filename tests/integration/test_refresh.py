from __future__ import annotations

import asyncio

import pytest

from niri_state.api.state import NiriState
from tests.factories.bundle import FakeBundle, FakeClient
from tests.factories.protocol import make_window


@pytest.mark.asyncio
async def test_refresh_replaces_snapshot() -> None:
    first = FakeBundle(client=FakeClient(windows=[make_window(id=100)]))
    second = FakeBundle(client=FakeClient(windows=[make_window(id=200)]))
    bundles = [first, second]
    state = NiriState()

    async def _open_bundle() -> FakeBundle:
        return bundles.pop(0)

    state._open_bundle = _open_bundle  # type: ignore[method-assign]
    await state.connect()
    before = state.snapshot
    assert 100 in state.snapshot.windows

    await state.refresh()
    await asyncio.sleep(0)
    after = state.snapshot

    assert 200 in after.windows
    assert after.revision > before.revision
    assert after.diagnostics.resync_count >= before.diagnostics.resync_count
    await state.close()
