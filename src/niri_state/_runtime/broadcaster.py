from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from niri_state._core.models.changes import ChangeSet
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state.config import SubscriberOverflowPolicy
from niri_state.errors import SubscriptionOverflowError


@dataclass(slots=True)
class Subscriber:
    id: int
    queue: asyncio.Queue[tuple[NiriSnapshot, ChangeSet | None]]
    cancelled: bool = False


class Broadcaster:
    def __init__(self, queue_size: int, overflow_policy: SubscriberOverflowPolicy) -> None:
        self._queue_size = queue_size
        self._overflow_policy = overflow_policy
        self._subscribers: dict[int, Subscriber] = {}
        self._next_subscriber_id = 0

    def subscribe(self) -> AsyncIterator[tuple[NiriSnapshot, ChangeSet | None]]:
        subscriber_id = self._next_subscriber_id
        self._next_subscriber_id += 1
        subscriber = Subscriber(
            id=subscriber_id,
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        self._subscribers[subscriber_id] = subscriber

        async def _iter() -> AsyncIterator[tuple[NiriSnapshot, ChangeSet | None]]:
            try:
                while not subscriber.cancelled:
                    item = await subscriber.queue.get()
                    yield item
            finally:
                self._subscribers.pop(subscriber_id, None)

        return _iter()

    async def publish(self, snapshot: NiriSnapshot, changeset: ChangeSet | None) -> None:
        for subscriber in list(self._subscribers.values()):
            if subscriber.cancelled:
                continue
            try:
                subscriber.queue.put_nowait((snapshot, changeset))
            except asyncio.QueueFull as exc:
                if self._overflow_policy is SubscriberOverflowPolicy.FAIL_FAST:
                    subscriber.cancelled = True
                    self._subscribers.pop(subscriber.id, None)
                    raise SubscriptionOverflowError(f"Subscriber {subscriber.id} queue overflow") from exc

                try:
                    subscriber.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    subscriber.queue.put_nowait((snapshot, changeset))
                except asyncio.QueueFull:
                    subscriber.cancelled = True
                    self._subscribers.pop(subscriber.id, None)

    async def close(self) -> None:
        for subscriber in self._subscribers.values():
            subscriber.cancelled = True
        self._subscribers.clear()
