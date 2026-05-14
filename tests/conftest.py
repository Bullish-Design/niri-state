from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from niri_state.api.health import HealthState
from niri_state.api.snapshot import Snapshot
from niri_state.core.broadcaster import PublishedState
from niri_state.core.diagnostics import Compatibility, Diagnostics
from tests.factories.bundle import FakeBundle
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_output,
    make_overview,
    make_window,
    make_workspace,
)

pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def fake_bundle() -> FakeBundle:
    return FakeBundle()


@pytest.fixture
def fake_runtime_bundle() -> FakeBundle:
    return FakeBundle()


class DummyState:
    def __init__(self) -> None:
        self._snapshot = Snapshot(
            revision=1,
            timestamp=0.0,
            health=HealthState.LIVE,
            outputs={"HDMI-A-1": make_output()},
            workspaces={1: make_workspace(id=1)},
            windows={100: make_window(id=100)},
            focused_workspace_id=1,
            focused_window_id=100,
            keyboard_layouts=make_keyboard_layouts(),
            overview=make_overview(),
            diagnostics=Diagnostics(),
            compatibility=Compatibility(),
        )

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshot

    async def subscribe(self) -> AsyncIterator[PublishedState]:
        if False:
            yield  # type: ignore[misc]  # pragma: no cover


@pytest.fixture
def dummy_state() -> DummyState:
    return DummyState()
