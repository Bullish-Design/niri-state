from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol, TypeVar

from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state.config import NiriStateConfig, WaitHealthPolicy
from niri_state.errors import WaitTimeoutError

T = TypeVar("T")


class WaitableState(Protocol):
    _config: NiriStateConfig

    @property
    def snapshot(self) -> NiriSnapshot | None: ...

    def subscribe(
        self,
    ) -> (
        AsyncIterator[tuple[NiriSnapshot, object | None]] | Awaitable[AsyncIterator[tuple[NiriSnapshot, object | None]]]
    ): ...


async def _subscription_iter(state: WaitableState) -> AsyncIterator[tuple[NiriSnapshot, object | None]]:
    maybe_iter = state.subscribe()
    if isinstance(maybe_iter, Awaitable):
        stream = await maybe_iter
    else:
        stream = maybe_iter
    async for item in stream:
        yield item


def _health_allows_wait(state: WaitableState, snapshot: NiriSnapshot) -> bool:
    policy = state._config.wait_health_policy
    if policy is WaitHealthPolicy.ALLOW_STALE:
        return True
    return snapshot.health is HealthState.LIVE


async def wait_until(
    state: WaitableState,
    predicate: Callable[[NiriSnapshot], bool],
    timeout: float | None = None,
) -> NiriSnapshot:
    async def _wait() -> NiriSnapshot:
        snap = state.snapshot
        if snap is not None and _health_allows_wait(state, snap) and predicate(snap):
            return snap

        async for snapshot, _ in _subscription_iter(state):
            if _health_allows_wait(state, snapshot) and predicate(snapshot):
                return snapshot

        raise WaitTimeoutError("Predicate never satisfied", timeout=timeout)

    try:
        if timeout is None:
            return await _wait()
        return await asyncio.wait_for(_wait(), timeout=timeout)
    except TimeoutError as exc:
        raise WaitTimeoutError("Predicate never satisfied", timeout=timeout, cause=exc) from exc


async def watch[T](
    state: WaitableState,
    selector: Callable[[NiriSnapshot], T],
) -> AsyncIterator[T]:
    prev: T | None = None
    async for snapshot, _ in _subscription_iter(state):
        current = selector(snapshot)
        if prev is None or current != prev:
            prev = current
            yield current


async def wait_for_selector[T](
    state: WaitableState,
    selector: Callable[[NiriSnapshot], T],
    predicate: Callable[[T], bool],
    timeout: float | None = None,
) -> T:
    snap = state.snapshot
    if snap is not None and _health_allows_wait(state, snap):
        current = selector(snap)
        if predicate(current):
            return current

    def pred(s: NiriSnapshot) -> bool:
        return predicate(selector(s))

    result = await wait_until(state, pred, timeout=timeout)
    return selector(result)
