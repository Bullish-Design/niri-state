from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable

from niri_state.adapters.protocol import NiriConnectionBundle
from niri_state.api.changes import (
    bootstrap_changeset,
    ChangeCause,
    ChangedDomain,
    close_changeset,
    event_changeset,
    health_changeset,
    refresh_changeset,
    resync_changeset,
)
from niri_state.api.config import InvariantFailurePolicy, NiriStateConfig, ResyncPolicy
from niri_state.api.errors import DesyncError, InvariantError, StateLifecycleError
from niri_state.api.health import HealthState, validate_transition
from niri_state.api.snapshot import Snapshot
from niri_state.core.bootstrap import run_bootstrap
from niri_state.core.broadcaster import Broadcaster, PublishedState
from niri_state.api.types import InvariantViolation
from niri_state.core.diagnostics import (
    with_desync,
    with_error,
    with_invariant_violations,
    with_resync,
)
from niri_state.core.engine_state import EngineState
from niri_state.core.invariants import collect_invariant_violations
from niri_state.core.reconcile import reconcile
from niri_state.core.reducers import reduce_event
from niri_state.core.resync import ResyncCoordinator
from niri_state.observability.logging import get_logger

_LOGGER = get_logger(__name__)

_FULL_DOMAINS = frozenset(
    {
        ChangedDomain.OUTPUTS,
        ChangedDomain.WORKSPACES,
        ChangedDomain.WINDOWS,
        ChangedDomain.FOCUS,
        ChangedDomain.KEYBOARD,
        ChangedDomain.OVERVIEW,
        ChangedDomain.HEALTH,
        ChangedDomain.DIAGNOSTICS,
    }
)


class NiriState:
    @classmethod
    async def open(
        cls,
        config: NiriStateConfig | None = None,
        *,
        bundle_factory: Callable[[], Awaitable[NiriConnectionBundle]] | None = None,
    ) -> NiriState:
        state = cls(config, bundle_factory=bundle_factory)
        await state.connect()
        return state

    def __init__(
        self,
        config: NiriStateConfig | None = None,
        *,
        bundle_factory: Callable[[], Awaitable[NiriConnectionBundle]] | None = None,
    ) -> None:
        self._config = config or NiriStateConfig()
        self._lock = asyncio.Lock()
        self._started = False
        self._closed = False

        self._bundle: NiriConnectionBundle | None = None
        self._engine: EngineState | None = None
        self._snapshot: Snapshot | None = None
        self._revision = 0

        self._mutation_task: asyncio.Task[None] | None = None
        self._broadcaster = Broadcaster(self._config)
        self._resync = ResyncCoordinator(self, self._config)

        if bundle_factory is not None:
            self._open_bundle = bundle_factory  # type: ignore[assignment]

    async def _open_bundle(self) -> NiriConnectionBundle:
        return await NiriConnectionBundle.open(config=self._config.pypc)

    @property
    def snapshot(self) -> Snapshot:
        if self._snapshot is None:
            raise StateLifecycleError(
                "state has not been started",
                operation="snapshot",
            )
        return self._snapshot

    def health(self) -> HealthState:
        if self._engine is None:
            return HealthState.BOOTSTRAPPING
        return self._engine.health

    async def subscribe(self) -> AsyncIterator[PublishedState]:
        if self._snapshot is not None:
            yield PublishedState(
                snapshot=self._snapshot,
                changes=bootstrap_changeset(revision=self._snapshot.revision),
            )
        async for published in self._broadcaster.subscribe():
            yield published

    def _install_bootstrap_outcome(self, outcome) -> None:
        self._engine = outcome.engine
        self._snapshot = outcome.initial_snapshot
        self._revision = outcome.initial_snapshot.revision

    def _start_mutation_loop(self) -> None:
        if self._mutation_task is None or self._mutation_task.done():
            _LOGGER.debug("starting mutation loop")
            self._mutation_task = asyncio.create_task(self._mutation_loop())

    async def _stop_mutation_loop(self) -> None:
        if self._mutation_task is None:
            return
        _LOGGER.debug("stopping mutation loop")
        self._mutation_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._mutation_task
        self._mutation_task = None

    async def connect(self) -> None:
        async with self._lock:
            if self._closed:
                raise StateLifecycleError(
                    "state is already closed",
                    operation="connect",
                )
            if self._started:
                raise StateLifecycleError(
                    "state is already started",
                    operation="connect",
                )

            _LOGGER.info("connect started")
            bundle = await self._open_bundle()
            try:
                outcome = await run_bootstrap(bundle, config=self._config)
            except Exception:
                _LOGGER.exception("connect bootstrap failed; closing opened bundle")
                await bundle.close()
                raise

            self._bundle = bundle
            self._install_bootstrap_outcome(outcome)

            await self._broadcaster.publish(
                PublishedState(
                    snapshot=outcome.initial_snapshot,
                    changes=outcome.initial_changeset,
                )
            )

            self._start_mutation_loop()
            await self._resync.start()
            self._started = True
            _LOGGER.info("connect completed")

    async def start(self) -> NiriState:
        await self.connect()
        return self

    async def __aenter__(self) -> NiriState:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()

    async def _mutation_loop(self) -> None:
        assert self._bundle is not None
        assert self._engine is not None

        async for event in self._bundle.events:
            if self._closed:
                return

            try:
                result = reduce_event(
                    self._engine,
                    event,
                    config=self._config,
                    revision=self._revision,
                )

                if not result.applied:
                    continue

                if result.marked_desync:
                    await self._transition_health(HealthState.STALE)

                reconcile(self._engine)

                self._revision += 1
                snapshot = self._engine.freeze(revision=self._revision)

                violations = collect_invariant_violations(snapshot)
                if violations:
                    snapshot = self._handle_invariant_violations(snapshot, violations)

                previous = self._snapshot
                self._snapshot = snapshot

                domains = result.domains
                if previous is not None and previous.health != snapshot.health:
                    domains = domains | frozenset({ChangedDomain.HEALTH, ChangedDomain.DIAGNOSTICS})

                await self._broadcaster.publish(
                    PublishedState(
                        snapshot=snapshot,
                        changes=event_changeset(
                            revision=snapshot.revision,
                            domains=domains,
                        ),
                    )
                )

            except DesyncError as exc:
                _LOGGER.warning("desync detected in mutation loop: %s", exc)
                await self._mark_desynced(exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOGGER.exception("mutation loop failed")
                await self._fail(exc)
                raise

    def _handle_invariant_violations(
        self,
        snapshot: Snapshot,
        violations: tuple[InvariantViolation, ...],
    ) -> Snapshot:
        policy = self._config.invariant_failure_policy

        if policy is InvariantFailurePolicy.FAIL:
            raise InvariantError(
                "snapshot invariants violated",
                violations=violations,
                revision=snapshot.revision,
                operation="publish_snapshot",
            )

        assert self._engine is not None
        self._engine.diagnostics = with_invariant_violations(
            self._engine.diagnostics,
            violations=violations,
        )
        self._engine.health = HealthState.STALE
        reconcile(self._engine)
        return self._engine.freeze(revision=snapshot.revision, timestamp=snapshot.timestamp)

    async def _transition_health(self, target: HealthState) -> None:
        assert self._engine is not None
        current = self._engine.health
        if current == target:
            return
        validate_transition(current, target)
        self._engine.health = target

    async def _mark_desynced(self, exc: DesyncError) -> None:
        assert self._engine is not None

        _LOGGER.warning("marking state stale due to desync: %s", exc)
        self._engine.diagnostics = with_desync(
            self._engine.diagnostics,
            reason=str(exc),
            event_type=exc.event_type or "UnknownEvent",
        )
        await self._transition_health(HealthState.STALE)
        reconcile(self._engine)

        self._revision += 1
        snapshot = self._engine.freeze(revision=self._revision)
        self._snapshot = snapshot

        await self._broadcaster.publish(
            PublishedState(
                snapshot=snapshot,
                changes=health_changeset(revision=snapshot.revision),
            )
        )

        if self._config.resync_policy is ResyncPolicy.AUTO:
            _LOGGER.info("requesting auto-resync after desync")
            self._resync.request()

    async def _fail(self, exc: Exception) -> None:
        assert self._engine is not None

        _LOGGER.error("transitioning state to failed: %s", exc)
        self._engine.diagnostics = with_error(
            self._engine.diagnostics,
            message=str(exc),
        )
        await self._transition_health(HealthState.FAILED)
        reconcile(self._engine)

        self._revision += 1
        snapshot = self._engine.freeze(revision=self._revision)
        self._snapshot = snapshot

        await self._broadcaster.publish(
            PublishedState(
                snapshot=snapshot,
                changes=health_changeset(revision=snapshot.revision),
            )
        )

    async def refresh(self, *, cause: ChangeCause = ChangeCause.REFRESH) -> Snapshot:
        async with self._lock:
            if self._bundle is None:
                raise StateLifecycleError(
                    "state is not connected",
                    operation="refresh",
                )
            if self._closed:
                raise StateLifecycleError(
                    "state is already closed",
                    operation="refresh",
                )

            _LOGGER.info("refresh started (cause=%s)", cause.value)
            old_bundle = self._bundle
            old_engine = self._engine

            await self._stop_mutation_loop()

            new_bundle: NiriConnectionBundle | None = None
            try:
                if old_engine is not None and old_engine.health in {HealthState.LIVE, HealthState.STALE}:
                    await self._transition_health(HealthState.RESYNCING)

                new_bundle = await self._open_bundle()
                outcome = await run_bootstrap(new_bundle, config=self._config)
            except Exception:
                if new_bundle is not None:
                    await new_bundle.close()
                self._bundle = old_bundle
                self._engine = old_engine
                self._start_mutation_loop()
                _LOGGER.exception("refresh failed; restored previous bundle and mutation loop")
                raise

            self._bundle = new_bundle
            self._engine = outcome.engine
            self._engine.diagnostics = with_resync(self._engine.diagnostics)
            if old_engine is not None:
                prev = old_engine.diagnostics
                self._engine.diagnostics = self._engine.diagnostics.model_copy(
                    update={
                        "event_count": prev.event_count + self._engine.diagnostics.event_count,
                        "resync_count": prev.resync_count + 1,
                    }
                )

            self._revision += 1
            self._snapshot = self._engine.freeze(revision=self._revision)

            await self._broadcaster.publish(
                PublishedState(
                    snapshot=self._snapshot,
                    changes=(
                        resync_changeset(revision=self._snapshot.revision, domains=_FULL_DOMAINS)
                        if cause is ChangeCause.RESYNC
                        else refresh_changeset(revision=self._snapshot.revision, domains=_FULL_DOMAINS)
                    ),
                )
            )

            self._start_mutation_loop()
            await old_bundle.close()
            _LOGGER.info("refresh completed (cause=%s)", cause.value)
            return self._snapshot

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return

            _LOGGER.info("close started")
            self._closed = True

            await self._stop_mutation_loop()

            if self._engine is not None and self._engine.health not in {HealthState.CLOSED, HealthState.FAILED}:
                await self._transition_health(HealthState.CLOSED)
                self._revision += 1
                self._snapshot = self._engine.freeze(revision=self._revision)

                await self._broadcaster.publish(
                    PublishedState(
                        snapshot=self._snapshot,
                        changes=close_changeset(revision=self._snapshot.revision),
                    )
                )

            try:
                if self._bundle is not None:
                    await self._bundle.close()
            finally:
                try:
                    await self._resync.close()
                finally:
                    await self._broadcaster.close()
            _LOGGER.info("close completed")
