from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

from niri_state.api.changes import ChangeSet
from niri_state.api.config import NiriStateConfig, SubscriberOverflowPolicy
from niri_state.api.errors import SubscriptionOverflowError
from niri_state.api.snapshot import Snapshot
from niri_state.observability.logging import get_logger

_LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PublishedState:
    snapshot: Snapshot
    changes: ChangeSet


@dataclass(eq=False, slots=True)
class _Subscriber:
    queue: asyncio.Queue[PublishedState | None]


class Broadcaster:
    def __init__(self, config: NiriStateConfig) -> None:
        self._config = config
        self._subscribers: set[_Subscriber] = set()
        self._closed = False

    def subscribe(self) -> AsyncIterator[PublishedState]:
        if self._closed:
            return self._empty()

        subscriber = _Subscriber(queue=asyncio.Queue(maxsize=self._config.subscriber_queue_size))
        self._subscribers.add(subscriber)
        return self._iter(subscriber)

    async def publish(self, item: PublishedState) -> None:
        if self._closed:
            return

        dead: list[_Subscriber] = []
        first_error: SubscriptionOverflowError | None = None

        for subscriber in self._subscribers:
            try:
                subscriber.queue.put_nowait(item)
            except asyncio.QueueFull:
                policy = self._config.subscriber_overflow_policy
                if policy is SubscriberOverflowPolicy.DROP_OLDEST:
                    _LOGGER.warning("subscriber queue full; dropping oldest item")
                    try:
                        _ = subscriber.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        subscriber.queue.put_nowait(item)
                    except asyncio.QueueFull as exc:
                        dead.append(subscriber)
                        if first_error is None:
                            first_error = SubscriptionOverflowError(
                                "subscriber queue remained full after dropping oldest item",
                                operation="broadcaster_publish",
                                cause=exc,
                            )
                else:
                    _LOGGER.error("subscriber queue overflowed with fail-fast policy")
                    dead.append(subscriber)
                    if first_error is None:
                        first_error = SubscriptionOverflowError(
                            "subscriber queue overflowed",
                            operation="broadcaster_publish",
                        )

        for subscriber in dead:
            with contextlib.suppress(asyncio.QueueFull):
                try:
                    _ = subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                subscriber.queue.put_nowait(None)
            self._subscribers.discard(subscriber)

        if first_error is not None:
            raise first_error

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        for subscriber in tuple(self._subscribers):
            try:
                subscriber.queue.put_nowait(None)
            except asyncio.QueueFull:
                # Drain into an unbounded queue so the sentinel doesn't
                # displace real data.
                unbounded: asyncio.Queue[PublishedState | None] = asyncio.Queue()
                while not subscriber.queue.empty():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        unbounded.put_nowait(subscriber.queue.get_nowait())
                unbounded.put_nowait(None)
                subscriber.queue = unbounded

        self._subscribers.clear()

    async def _iter(self, subscriber: _Subscriber) -> AsyncIterator[PublishedState]:
        try:
            while True:
                item = await subscriber.queue.get()
                if item is None:
                    return
                yield item
        finally:
            self._subscribers.discard(subscriber)

    async def _empty(self) -> AsyncIterator[PublishedState]:
        if False:
            yield  # pragma: no cover
        return
