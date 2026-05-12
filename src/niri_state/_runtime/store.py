from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from niri_pypc import NiriConnectionBundle

from niri_state._core.invariants import assert_invariants
from niri_state._core.models.changes import ChangeCause, ChangedDomain, ChangeSet
from niri_state._core.models.draft import DraftState
from niri_state._core.models.health import HealthState, validate_transition
from niri_state._core.models.snapshot import NiriSnapshot
from niri_state._core.reducers.root import reduce_event
from niri_state._runtime.broadcaster import Broadcaster
from niri_state._runtime.resync import ResyncCoordinator
from niri_state.config import InvariantFailurePolicy, NiriStateConfig
from niri_state.errors import StateLifecycleError


class NiriState:
    """Main state management class.

    Owns the single mutation loop that processes events from the event stream
    and publishes immutable snapshots to all subscribers.
    """

    def __init__(self, config: NiriStateConfig) -> None:
        self._config = config
        self._current_snapshot: NiriSnapshot | None = None
        self._revision = 0
        self._bundle: NiriConnectionBundle | None = None
        self._mutation_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()
        self._logger = logging.getLogger("niri_state.store")
        self._broadcaster = Broadcaster(
            queue_size=self._config.subscriber_queue_size,
            overflow_policy=self._config.subscriber_overflow_policy,
        )
        self._resync_coordinator = ResyncCoordinator(self, self._config)

    @classmethod
    async def start(cls, config: NiriStateConfig | None = None) -> NiriState:
        from niri_state._runtime.bootstrap import run_bootstrap

        cfg = config if config is not None else NiriStateConfig()
        outcome = await run_bootstrap(cfg)
        state = cls(cfg)
        await state.connect(outcome.initial_snapshot, outcome.bundle)
        return state

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
                raise StateLifecycleError("Already connected", current_state="connected")

            self._bundle = bundle
            self._current_snapshot = initial_snapshot
            self._revision = initial_snapshot.revision
            self._shutdown_event.clear()
            await self._broadcast(initial_snapshot, None)
            self._mutation_task = asyncio.create_task(self._mutation_loop(bundle))

    async def _mutation_loop(self, bundle: NiriConnectionBundle) -> None:
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
                    self._resync_coordinator.mark_stale(f"event stream error: {exc}")
                    break

                snapshot = self._current_snapshot
                if snapshot is None:
                    break

                draft = DraftState.from_snapshot(snapshot)
                result = reduce_event(draft, event, policy)

                if result.changed_domains or result.applied:
                    next_snapshot = draft.freeze(revision=self._revision + 1)

                    if invariant_policy is InvariantFailurePolicy.FAIL:
                        try:
                            assert_invariants(next_snapshot)
                        except Exception as exc:
                            self._logger.error("Invariant violation: %s", exc)
                            await self._transition_health(HealthState.FAILED, f"invariant violation: {exc}")
                            break

                    self._revision = next_snapshot.revision
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
        await self._broadcaster.publish(snapshot, changeset)

    async def _transition_health(self, new_health: HealthState, reason: str) -> None:
        snapshot = self._current_snapshot
        if snapshot is None:
            return

        current = snapshot.health
        try:
            validate_transition(current, new_health, reason=reason)
        except StateLifecycleError:
            return

        draft = DraftState.from_snapshot(snapshot)
        draft.health = new_health
        diagnostics_update = cast(dict[str, Any], {"last_transition_reason": reason})
        draft.diagnostics = draft.diagnostics.model_copy(update=diagnostics_update)
        next_snapshot = draft.freeze(revision=self._revision + 1)
        self._revision = next_snapshot.revision

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

        async def _iter() -> AsyncIterator[tuple[NiriSnapshot, ChangeSet | None]]:
            snapshot = self._current_snapshot
            if snapshot is not None:
                yield (snapshot, None)
            async for item in self._broadcaster.subscribe():
                yield item

        return _iter()

    async def refresh(self) -> None:
        """Force a resync. Used in MANUAL resync policy."""
        from niri_state._runtime.bootstrap import run_bootstrap

        await self._transition_health(HealthState.RESYNCING, "manual refresh")
        old_bundle = self._bundle
        old_task = self._mutation_task
        self._shutdown_event.set()
        if old_task is not None:
            old_task.cancel()
            try:
                await old_task
            except asyncio.CancelledError:
                pass
        self._mutation_task = None

        outcome = await run_bootstrap(self._config)
        next_revision = self._revision + 1
        next_snapshot = outcome.initial_snapshot.model_copy(update={"revision": next_revision})
        next_changeset = outcome.initial_changeset.model_copy(
            update={"revision": next_revision, "timestamp": next_snapshot.timestamp}
        )

        self._bundle = outcome.bundle
        self._current_snapshot = next_snapshot
        self._revision = next_snapshot.revision

        self._shutdown_event.clear()
        self._mutation_task = asyncio.create_task(self._mutation_loop(outcome.bundle))

        if old_bundle is not None:
            try:
                await old_bundle.close()
            except Exception:
                pass

        await self._broadcast(next_snapshot, next_changeset)

    async def close(self) -> None:
        """Idempotent shutdown."""
        if self._shutdown_event.is_set():
            return

        await self._transition_health(HealthState.CLOSED, "close called")
        self._shutdown_event.set()

        if self._mutation_task is not None:
            self._mutation_task.cancel()
            try:
                await self._mutation_task
            except asyncio.CancelledError:
                pass

        await self._broadcaster.close()

        if self._bundle is not None:
            try:
                await self._bundle.close()
            except Exception:
                pass
            self._bundle = None
