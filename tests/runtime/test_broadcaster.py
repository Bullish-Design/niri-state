from __future__ import annotations

import asyncio

import pytest
from niri_pypc.types.generated.models import KeyboardLayouts

from niri_state._core.models.changes import ChangeCause, ChangeSet
from niri_state._core.models.entities import KeyboardState, OverviewState
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import CompatibilityInfo, DiagnosticsInfo, NiriSnapshot
from niri_state._runtime.broadcaster import Broadcaster
from niri_state.config import SubscriberOverflowPolicy
from niri_state.errors import SubscriptionOverflowError


def _make_snapshot(revision: int = 1) -> NiriSnapshot:
    return NiriSnapshot(
        revision=revision,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_output_name=None,
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard=KeyboardState(protocol=KeyboardLayouts(current_idx=0, names=["us"]), current_name="us"),
        overview=OverviewState(is_open=False),
        workspaces_by_output={},
        windows_by_workspace={},
        active_workspace_by_output={},
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(),
    )


def _make_changeset(revision: int) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        timestamp=0.0,
        cause=ChangeCause.EVENT,
        changed_domains=frozenset(),
    )


async def test_drop_oldest_overflow_keeps_latest() -> None:
    broadcaster = Broadcaster(queue_size=1, overflow_policy=SubscriberOverflowPolicy.DROP_OLDEST)
    stream = broadcaster.subscribe()

    await broadcaster.publish(_make_snapshot(1), _make_changeset(1))
    await broadcaster.publish(_make_snapshot(2), _make_changeset(2))

    snap, _ = await asyncio.wait_for(stream.__anext__(), timeout=0.5)
    assert snap.revision == 2


async def test_fail_fast_overflow_raises() -> None:
    broadcaster = Broadcaster(queue_size=1, overflow_policy=SubscriberOverflowPolicy.FAIL_FAST)
    _ = broadcaster.subscribe()

    await broadcaster.publish(_make_snapshot(1), _make_changeset(1))
    with pytest.raises(SubscriptionOverflowError):
        await broadcaster.publish(_make_snapshot(2), _make_changeset(2))
