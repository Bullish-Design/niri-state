from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from tests.factories.protocol import make_keyboard_layouts, make_output, make_overview, make_window, make_workspace

from niri_state.broadcaster import PublishedState
from niri_state.changes import ChangeCause, ChangeSet
from niri_state.config import NiriStateConfig
from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.snapshot import Snapshot
from niri_state.waiters import wait_until, watch


@pytest.mark.asyncio
async def test_wait_until_returns_immediately_when_predicate_matches(dummy_state) -> None:
    snapshot = await wait_until(
        dummy_state,
        lambda s: True,
        config=NiriStateConfig(),
        timeout=0.1,
    )
    assert snapshot is dummy_state.snapshot


class _WatchState:
    def __init__(self) -> None:
        self._snapshots = [
            Snapshot(
                revision=1,
                timestamp=1.0,
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
            ),
            Snapshot(
                revision=2,
                timestamp=2.0,
                health=HealthState.LIVE,
                outputs={"HDMI-A-1": make_output()},
                workspaces={1: make_workspace(id=1)},
                windows={101: make_window(id=101)},
                focused_workspace_id=1,
                focused_window_id=101,
                keyboard_layouts=make_keyboard_layouts(),
                overview=make_overview(),
                diagnostics=Diagnostics(),
                compatibility=Compatibility(),
            ),
        ]

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshots[0]

    async def subscribe(self) -> AsyncIterator[PublishedState]:
        yield PublishedState(snapshot=self._snapshots[0], changes=empty_changeset(1))
        yield PublishedState(snapshot=self._snapshots[1], changes=empty_changeset(2))


def empty_changeset(revision: int) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        cause=ChangeCause.EVENT,
        domains=frozenset(),
    )


@pytest.mark.asyncio
async def test_watch_skips_duplicate_initial_snapshot() -> None:
    state = _WatchState()

    revisions: list[int] = []
    async for snapshot in watch(state):
        revisions.append(snapshot.revision)
        if len(revisions) == 2:
            break

    assert revisions == [1, 2]
