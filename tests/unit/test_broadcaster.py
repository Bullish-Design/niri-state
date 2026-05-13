from __future__ import annotations

import pytest

from niri_state.broadcaster import Broadcaster


@pytest.mark.asyncio
async def test_broadcaster_subscribe_returns_iterator() -> None:
    from niri_state.config import NiriStateConfig

    broadcaster = Broadcaster(NiriStateConfig())
    subscription = broadcaster.subscribe()
    assert subscription is not None
