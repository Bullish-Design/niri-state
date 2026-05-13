from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_refresh_replaces_snapshot(fake_runtime_bundle) -> None:
    # Required: implement using the bundle seam in NiriState._open_bundle.
    assert True
