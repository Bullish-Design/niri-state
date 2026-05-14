from __future__ import annotations

import asyncio

import pytest
from tests.factories.protocol import make_keyboard_layouts, make_output, make_overview

from niri_state.api.changes import ChangeCause, ChangeSet
from niri_state.api.config import NiriStateConfig, SubscriberOverflowPolicy
from niri_state.api.errors import SubscriptionOverflowError
from niri_state.api.health import HealthState
from niri_state.api.snapshot import Snapshot
from niri_state.core.broadcaster import Broadcaster, PublishedState
from niri_state.core.diagnostics import Compatibility, Diagnostics


def _make_published(revision: int = 1) -> PublishedState:
    snapshot = Snapshot(
        revision=revision,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={"HDMI-A-1": make_output()},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )
    return PublishedState(
        snapshot=snapshot,
        changes=ChangeSet(revision=revision, cause=ChangeCause.EVENT, domains=frozenset()),
    )


@pytest.mark.asyncio
async def test_broadcaster_subscribe_returns_iterator() -> None:
    broadcaster = Broadcaster(NiriStateConfig())
    subscription = broadcaster.subscribe()
    assert subscription is not None


@pytest.mark.asyncio
async def test_publish_delivers_to_all_subscribers() -> None:
    config = NiriStateConfig(subscriber_queue_size=8)
    broadcaster = Broadcaster(config)
    sub1 = broadcaster.subscribe()
    sub2 = broadcaster.subscribe()

    item = _make_published()
    await broadcaster.publish(item)
    await broadcaster.close()

    items1 = [x async for x in sub1]
    items2 = [x async for x in sub2]
    assert len(items1) == 1
    assert len(items2) == 1


@pytest.mark.asyncio
async def test_publish_overflow_still_delivers_to_healthy_subscribers() -> None:
    config = NiriStateConfig(
        subscriber_queue_size=2,
        subscriber_overflow_policy=SubscriberOverflowPolicy.FAIL_FAST,
    )
    broadcaster = Broadcaster(config)
    _slow_sub = broadcaster.subscribe()
    fast_sub = broadcaster.subscribe()

    received: list[PublishedState] = []

    async def drain() -> None:
        async for item in fast_sub:
            received.append(item)

    task = asyncio.create_task(drain())
    await asyncio.sleep(0)  # let drain() start waiting on queue.get()

    await broadcaster.publish(_make_published(revision=1))
    await asyncio.sleep(0)  # let drain() consume
    await broadcaster.publish(_make_published(revision=2))
    await asyncio.sleep(0)  # let drain() consume

    # slow_sub queue is full (2 items), fast_sub queue is empty (drained)
    # only slow_sub overflows
    with pytest.raises(SubscriptionOverflowError):
        await broadcaster.publish(_make_published(revision=3))

    await broadcaster.close()
    await task

    assert len(received) == 3


@pytest.mark.asyncio
async def test_publish_drop_oldest_on_full_queue() -> None:
    config = NiriStateConfig(
        subscriber_queue_size=1,
        subscriber_overflow_policy=SubscriberOverflowPolicy.DROP_OLDEST,
    )
    broadcaster = Broadcaster(config)
    sub = broadcaster.subscribe()

    await broadcaster.publish(_make_published(revision=1))
    await broadcaster.publish(_make_published(revision=2))
    await broadcaster.close()

    items = [x async for x in sub]
    assert len(items) == 1
    assert items[0].snapshot.revision == 2
