from __future__ import annotations

import asyncio

import pytest

from niri_state._core.models.changes import ChangeCause, ChangeSet
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._runtime.broadcaster import Broadcaster
from niri_state.config import SubscriberOverflowPolicy
from niri_state.errors import SubscriptionOverflowError
from tests._typing_helpers import make_minimal_snapshot


def _make_snapshot(revision: int = 1) -> NiriSnapshot:
    return make_minimal_snapshot(revision=revision)


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


async def test_close_wakes_waiting_subscriber() -> None:
    broadcaster = Broadcaster(queue_size=1, overflow_policy=SubscriberOverflowPolicy.DROP_OLDEST)
    stream = broadcaster.subscribe()

    waiter = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)
    await broadcaster.close()

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(waiter, timeout=0.5)
