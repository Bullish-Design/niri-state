from __future__ import annotations

import pytest

from niri_state.config import NiriStateConfig
from niri_state.waiters import wait_until


@pytest.mark.asyncio
async def test_wait_until_returns_immediately_when_predicate_matches(dummy_state) -> None:
    snapshot = await wait_until(
        dummy_state,
        lambda s: True,
        config=NiriStateConfig(),
        timeout=0.1,
    )
    assert snapshot is dummy_state.snapshot
