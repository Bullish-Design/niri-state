from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import TypeVar

from niri_pypc import NiriConnectionBundle

from niri_state._core.invariants import assert_invariants
from niri_state._core.models.changes import ChangeCause, ChangedDomain, ChangeSet
from niri_state._core.models.draft import DraftState
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._core.reducers.root import reduce_event
from niri_state.config import (
    InvariantFailurePolicy,
    NiriStateConfig,
    SubscriberOverflowPolicy,
)
from niri_state.errors import StateLifecycleError


class Subscriber:
    """A single subscriber on the broadcast channel."""

    def __init__(
        self,
        id_: int,
        queue: asyncio.Queue[tuple[NiriSnapshot, ChangeSet | None]],
    ) -> None:
        self.id = id_
        self.queue = queue
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class SubscriberOverflowError(Exception):
    pass


class NiriState:
    """Main state management class.

    Owns the single mutation loop that processes events from the event stream
    and publishes immutable snapshots to all subscribers.
    """

    def __init__(self, config: NiriStateConfig) -> None:
        self._config = config
        self._current_snapshot: NiriSnapshot | None = None
        self._current_draft: DraftState | None = None
        self._revision = 0
        self._bundle: NiriConnectionBundle | None = None
        self._mutation_task: asyncio.Task[None] | None = None
        self._subscribers: dict[int, Subscriber] = {}
        self._subscriber_counter = 0
        self._shutdown_event = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()
        self._logger = logging.getLogger("niri_state.store")

    @property
    def snapshot(self) -> NiriSnapshot | None:
        return self._current_snapshot

    @property
    def health(self) -> HealthState:
        if self._current_snapshot is None:
            return HealthState.BOOTSTRAPPING
        return self._current_snapshot.health

    async def connect(self, initial_snapshot: NiriSnapshot, bundle: NiriConnectionBundle) -> None:
        """Set up runtime with bootstrap outcome. Called once after bootstrap."""
        async with self._lifecycle_lock:
            if self._bundle is not None:
                raise StateLifecycleError(
                    "Already connected",
                    current_state="connected",
                )

            self._bundle = bundle
            self._current_snapshot = initial_snapshot
            self._revision = initial_snapshot.revision

            self._mutation_task = asyncio.create_task(self._mutation_loop())

    async def _mutation_loop(self) -> None:
        """Single-owner mutation loop. Processes events from the event stream."""
        bundle = self._bundle
        if bundle is None:
            return

        policy = self._config.unknown_event_policy
        invariant_policy = self._config.invariant_failure_policy

        try:
            while not self._shutdown_event.is_set():
                try:
                    event = await bundle.events.next(timeout=0.1)
                except TimeoutError:
                    continue
                except Exception as exc:
                    self._logger.warning("Event stream error: %s", exc)
                    await self._transition_health(HealthState.STALE, f"event stream error: {exc}")
                    break

                if self._current_snapshot is None or self._current_draft is None:
                    raise RuntimeError("No current snapshot to create draft from")
                self._current_draft = DraftState.from_snapshot(self._current_snapshot)

                result = reduce_event(self._current_draft, event, policy.value)

                if result.changed_domains or result.applied:
                    next_snapshot = self._current_draft.freeze(revision=self._revision + 1)
                    self._revision += 1

                    if invariant_policy is InvariantFailurePolicy.FAIL:
                        try:
                            assert_invariants(next_snapshot)
                        except Exception as exc:
                            self._logger.error("Invariant violation: %s", exc)
                            await self._transition_health(HealthState.FAILED, f"invariant violation: {exc}")
                            break

                    changeset = ChangeSet(
                        revision=next_snapshot.revision,
                        timestamp=next_snapshot.timestamp,
                        cause=ChangeCause.EVENT,
                        changed_domains=result.changed_domains,
                        event_type=result.event_type,
                        event_summary=result.event_summary,
                    )

                    self._current_snapshot = next_snapshot
                    await self._broadcast(next_snapshot, changeset)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._logger.error("Mutation loop error: %s", exc)
            await self._transition_health(HealthState.FAILED, f"mutation loop error: {exc}")

    async def _broadcast(self, snapshot: NiriSnapshot, changeset: ChangeSet | None) -> None:
        """Publish snapshot to all active subscribers."""
        for sub in list(self._subscribers.values()):
            if sub.is_cancelled:
                continue

            try:
                sub.queue.put_nowait((snapshot, changeset))
            except asyncio.QueueFull:
                if self._config.subscriber_overflow_policy is SubscriberOverflowPolicy.FAIL_FAST:
                    sub.cancel()
                    self._subscribers.pop(sub.id, None)
                    self._logger.warning("Subscriber %d overflow, cancelled", sub.id)
                else:
                    try:
                        sub.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        sub.queue.put_nowait((snapshot, changeset))
                    except asyncio.QueueFull:
                        sub.cancel()
                        self._subscribers.pop(sub.id, None)

    async def _transition_health(self, new_health: HealthState, reason: str) -> None:
        """Transition health state if legal."""
        from niri_state._core.models.health import validate_transition

        if self._current_snapshot is None:
            return

        current = self._current_snapshot.health
        try:
            validate_transition(current, new_health, reason=reason)
        except StateLifecycleError:
            return

        if self._current_draft is None:
            self._current_draft = DraftState.from_snapshot(self._current_snapshot)

        self._current_draft.health = new_health
        self._current_draft.diagnostics = self._current_draft.diagnostics.model_copy(
            update={"last_transition_reason": reason}
        )
        next_snapshot = self._current_draft.freeze(revision=self._revision + 1)
        self._revision += 1

        changeset = ChangeSet(
            revision=next_snapshot.revision,
            timestamp=next_snapshot.timestamp,
            cause=ChangeCause.LIFECYCLE,
            changed_domains=frozenset({ChangedDomain.HEALTH}),
            event_type=None,
            event_summary=f"health transition: {reason}",
        )

        self._current_snapshot = next_snapshot
        await self._broadcast(next_snapshot, changeset)

    def subscribe(self) -> AsyncIterator[tuple[NiriSnapshot, ChangeSet | None]]:
        """Subscribe to state publications. Returns an async iterator."""
        sub_id = self._subscriber_counter
        self._subscriber_counter += 1
        queue: asyncio.Queue[tuple[NiriSnapshot, ChangeSet | None]] = asyncio.Queue(
            maxsize=self._config.subscriber_queue_size
        )
        sub = Subscriber(sub_id, queue)
        self._subscribers[sub_id] = sub

        async def _iter() -> AsyncIterator[tuple[NiriSnapshot, ChangeSet | None]]:
            try:
                while not sub.is_cancelled:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield item
                    except TimeoutError:
                        if sub.is_cancelled:
                            break
                        continue
            finally:
                self._subscribers.pop(sub_id, None)

        return _iter()

    async def refresh(self) -> None:
        """Force a resync. Used in MANUAL resync policy."""
        from niri_state._runtime.bootstrap import run_bootstrap

        if self._bundle is None:
            return

        await self._transition_health(HealthState.RESYNCING, "manual refresh")

        outcome = await run_bootstrap(self._config)

        self._current_snapshot = outcome.initial_snapshot
        self._revision = outcome.initial_snapshot.revision
        self._bundle = outcome.bundle

    async def close(self) -> None:
        """Idempotent shutdown."""
        if self._shutdown_event.is_set():
            return

        self._shutdown_event.set()

        if self._mutation_task is not None:
            self._mutation_task.cancel()
            try:
                await self._mutation_task
            except asyncio.CancelledError:
                pass

        for sub in self._subscribers.values():
            sub.cancel()
        self._subscribers.clear()

        if self._bundle is not None:
            try:
                await self._bundle.close()
            except Exception:
                pass
            self._bundle = None

        await self._transition_health(HealthState.CLOSED, "close called")


T = TypeVar("T")


async def wait_until(
    state: NiriState,
    predicate: Callable[[NiriSnapshot], bool],
    timeout: float | None = None,
) -> NiriSnapshot:
    """Wait until predicate returns True for current snapshot."""
    snap = state.snapshot
    if snap is not None and predicate(snap):
        return snap

    async for snapshot, _ in state.subscribe():
        if predicate(snapshot):
            return snapshot

    raise TimeoutError("Predicate never satisfied")


async def watch(
    state: NiriState,
    selector: Callable[[NiriSnapshot], T],
) -> AsyncIterator[T]:
    """Watch selector values, emitting only on changes."""
    prev: T | None = None
    async for snapshot, _ in state.subscribe():
        current = selector(snapshot)
        if prev is None or current != prev:
            prev = current
            yield current
