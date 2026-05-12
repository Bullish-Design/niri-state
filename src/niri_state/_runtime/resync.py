from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from niri_state._core.models.health import HealthState
from niri_state.config import NiriStateConfig, ResyncPolicy

if TYPE_CHECKING:
    from niri_state._runtime.store import NiriState


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
            self._trigger_stale_transition(reason)

        if self._config.resync_policy is ResyncPolicy.AUTO:
            self._start_auto_resync()

    def _trigger_stale_transition(self, reason: str) -> None:
        asyncio.create_task(self._state._transition_health(HealthState.STALE, reason))

    def _start_auto_resync(self) -> None:
        if self._resync_task is not None and not self._resync_task.done():
            return
        self._resync_task = asyncio.create_task(self._resync_loop())

    async def _resync_loop(self) -> None:
        max_attempts = self._config.resync_max_attempts
        backoff_base = self._config.resync_backoff_base

        for attempt in range(max_attempts):
            self._logger.info("Auto-resync attempt %d/%d", attempt + 1, max_attempts)
            try:
                await self._state.refresh()
                self._logger.info("Auto-resync succeeded on attempt %d", attempt + 1)
                return
            except Exception as exc:
                self._logger.warning("Auto-resync attempt %d failed: %s", attempt + 1, exc)
                if attempt < max_attempts - 1:
                    await asyncio.sleep(backoff_base * (2**attempt))

        await self._state._transition_health(HealthState.FAILED, "auto resync exhausted")

    async def force_resync(self) -> None:
        self._logger.info("Force resync requested")
        if self._resync_task is not None and not self._resync_task.done():
            self._resync_task.cancel()
            try:
                await self._resync_task
            except asyncio.CancelledError:
                pass

        await self._state.refresh()


def create_resync_coordinator(state: NiriState, config: NiriStateConfig) -> ResyncCoordinator:
    return ResyncCoordinator(state, config)
