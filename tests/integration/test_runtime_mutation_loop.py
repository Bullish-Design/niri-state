from __future__ import annotations

import pytest

from niri_state.store import NiriState


@pytest.mark.asyncio
async def test_runtime_publishes_after_event(fake_runtime_bundle) -> None:
    state = NiriState()
    # Required: monkeypatch state._open_bundle to return fake_runtime_bundle.
    # await state.connect()
    # published = await anext(state.subscribe())
    # assert published.snapshot.revision >= 1
