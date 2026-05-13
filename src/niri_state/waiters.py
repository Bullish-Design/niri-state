from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Protocol

from niri_state.broadcaster import PublishedState
from niri_state.config import NiriStateConfig, WaitHealthPolicy
from niri_state.errors import WaitTimeoutError
from niri_state.health import HealthState
from niri_state.snapshot import Snapshot


class WaitableState(Protocol):
    @property
    def snapshot(self) -> Snapshot: ...
    def subscribe(self) -> AsyncIterator[PublishedState]: ...


def _health_allows_wait(
    *,
    snapshot: Snapshot,
    config: NiriStateConfig,
) -> bool:
    if config.wait_health_policy is WaitHealthPolicy.ALLOW_STALE:
        return snapshot.health in {HealthState.LIVE, HealthState.STALE}
    return snapshot.health is HealthState.LIVE


async def _subscription_iter(state: WaitableState) -> AsyncIterator[Snapshot]:
    async for published in state.subscribe():
        yield published.snapshot


async def watch(state: WaitableState) -> AsyncIterator[Snapshot]:
    yield state.snapshot
    async for snapshot in _subscription_iter(state):
        yield snapshot


async def wait_until(
    state: WaitableState,
    predicate: Callable[[Snapshot], bool],
    *,
    config: NiriStateConfig,
    timeout: float | None = None,
) -> Snapshot:
    current = state.snapshot
    if _health_allows_wait(snapshot=current, config=config) and predicate(current):
        return current

    async def _wait() -> Snapshot:
        async for snapshot in _subscription_iter(state):
            if not _health_allows_wait(snapshot=snapshot, config=config):
                continue
            if predicate(snapshot):
                return snapshot
        raise WaitTimeoutError(
            "state subscription closed before predicate matched",
            timeout=timeout or 0.0,
            operation="wait_until",
        )

    try:
        if timeout is None:
            return await _wait()
        return await asyncio.wait_for(_wait(), timeout=timeout)
    except TimeoutError as exc:
        raise WaitTimeoutError(
            "timed out waiting for state predicate",
            timeout=timeout or 0.0,
            operation="wait_until",
            cause=exc,
        ) from exc


async def wait_for_selector[T](
    state: WaitableState,
    selector: Callable[[Snapshot], T],
    *,
    predicate: Callable[[T], bool] | None = None,
    config: NiriStateConfig,
    timeout: float | None = None,
) -> T:
    def _wrapped(snapshot: Snapshot) -> bool:
        value = selector(snapshot)
        if predicate is None:
            return bool(value)
        return predicate(value)

    snapshot = await wait_until(
        state,
        _wrapped,
        config=config,
        timeout=timeout,
    )
    return selector(snapshot)
