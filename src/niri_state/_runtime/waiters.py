from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import TypeVar

from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._runtime.store import NiriState
from niri_state.errors import WaitTimeoutError

T = TypeVar("T")


async def wait_until(
    state: NiriState,
    predicate: Callable[[NiriSnapshot], bool],
    timeout: float | None = None,
) -> NiriSnapshot:
    snap = state.snapshot
    if snap is not None and predicate(snap):
        return snap

    try:
        async for snapshot, _ in state.subscribe():
            if predicate(snapshot):
                return snapshot
    except asyncio.CancelledError:
        raise

    raise WaitTimeoutError("Predicate never satisfied", timeout=timeout)


async def watch[T](
    state: NiriState,
    selector: Callable[[NiriSnapshot], T],
) -> AsyncIterator[T]:
    prev: T | None = None
    async for snapshot, _ in state.subscribe():
        current = selector(snapshot)
        if prev is None or current != prev:
            prev = current
            yield current


async def wait_for_selector[T](
    state: NiriState,
    selector: Callable[[NiriSnapshot], T],
    predicate: Callable[[T], bool],
    timeout: float | None = None,
) -> T:
    current = selector(state.snapshot) if state.snapshot is not None else None
    if current is not None and predicate(current):
        return current

    def pred(snap: NiriSnapshot) -> bool:
        return predicate(selector(snap))

    snap = await wait_until(state, pred, timeout=timeout)
    return selector(snap)
