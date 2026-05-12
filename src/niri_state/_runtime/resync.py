from __future__ import annotations

import asyncio
import logging

from niri_state._core.models.health import HealthState
from niri_state._runtime.bootstrap import run_bootstrap
from niri_state._runtime.store import NiriState
from niri_state.config import NiriStateConfig, ResyncPolicy


class ResyncCoordinator:
    """Handles resync/recovery coordination with policy enforcement."""

    def __init__(self, state: NiriState, config: NiriStateConfig) -> None:
        self._state = state
        self._config = config
        self._logger = logging.getLogger("niri_state.resync")
        self._resync_task: asyncio.Task[None] | None = None

    @property
    def policy(self) -> ResyncPolicy:
        return self._config.resync_policy

    def mark_stale(self, reason: str, *, event_type: str | None = None) -> None:
        """Mark the state as stale. Triggers resync if policy is AUTO."""
        self._logger.warning("State marked stale: %s (event_type=%s)", reason, event_type)

        if self._state.health != HealthState.STALE:
            try:
                self._trigger_stale_transition(reason)
            except Exception as exc:
                self._logger.error("Failed to transition to STALE: %s", exc)
                return

        if self._config.resync_policy is ResyncPolicy.AUTO:
            self._start_auto_resync()

    def _trigger_stale_transition(self, reason: str) -> None:
        """Trigger transition to STALE. May be overridden by subclass or store."""
        pass

    def _start_auto_resync(self) -> None:
        """Start the auto-resync loop."""
        if self._resync_task is not None and not self._resync_task.done():
            return

        self._resync_task = asyncio.create_task(self._resync_loop())

    async def _resync_loop(self) -> None:
        """Auto-resync loop with retry and backoff."""
        max_attempts = self._config.resync_max_attempts
        backoff_base = self._config.resync_backoff_base

        for attempt in range(max_attempts):
            self._logger.info("Auto-resync attempt %d/%d", attempt + 1, max_attempts)
            try:
                await self._attempt_resync()
                self._logger.info("Auto-resync succeeded on attempt %d", attempt + 1)
                return
            except Exception as exc:
                self._logger.warning("Auto-resync attempt %d failed: %s", attempt + 1, exc)
                if attempt < max_attempts - 1:
                    wait_time = backoff_base * (2**attempt)
                    await asyncio.sleep(wait_time)

        self._logger.error("Auto-resync exhausted all attempts")

    async def _attempt_resync(self) -> None:
        """Execute a single resync attempt."""
        outcome = await run_bootstrap(self._config)
        self._state._current_snapshot = outcome.initial_snapshot
        self._state._revision = outcome.initial_snapshot.revision
        if self._state._bundle is not None:
            try:
                await self._state._bundle.close()
            except Exception:
                pass
        self._state._bundle = outcome.bundle

    async def force_resync(self) -> None:
        """Force an immediate resync regardless of policy."""
        self._logger.info("Force resync requested")
        if self._resync_task is not None and not self._resync_task.done():
            self._resync_task.cancel()
            try:
                await self._resync_task
            except asyncio.CancelledError:
                pass

        await self._attempt_resync()


def create_resync_coordinator(state: NiriState, config: NiriStateConfig) -> ResyncCoordinator:
    """Factory function to create a resync coordinator."""
    return ResyncCoordinator(state, config)
