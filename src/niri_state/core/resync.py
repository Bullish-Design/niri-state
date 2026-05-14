from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

from niri_state.changes import ChangeCause
from niri_state.config import NiriStateConfig, ResyncPolicy
from niri_state.observability.logging import get_logger

_LOGGER = get_logger(__name__)


class _Refreshable(Protocol):
    async def refresh(self, *, cause: ChangeCause = ChangeCause.REFRESH): ...


class ResyncCoordinator:
    def __init__(self, state: _Refreshable, config: NiriStateConfig) -> None:
        self._state = state
        self._config = config
        self._trigger = asyncio.Event()
        self._closed = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        if self._config.resync_policy is not ResyncPolicy.AUTO:
            return
        _LOGGER.info("starting auto-resync coordinator")
        self._task = asyncio.create_task(self._run())

    def request(self) -> None:
        if self._closed:
            return
        _LOGGER.info("auto-resync requested")
        self._trigger.set()

    async def _run(self) -> None:
        while not self._closed:
            await self._trigger.wait()
            self._trigger.clear()

            if self._closed:
                return

            await self._run_attempts()

    async def _run_attempts(self) -> None:
        max_attempts = int(self._config.resync_max_attempts)
        backoff_base = float(self._config.resync_backoff_base)

        for attempt in range(max_attempts):
            try:
                await self._state.refresh(cause=ChangeCause.RESYNC)
                _LOGGER.info("auto-resync succeeded on attempt %d", attempt + 1)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt + 1 >= max_attempts:
                    _LOGGER.warning("auto-resync exhausted after %d attempts: %s", max_attempts, exc)
                    return
                delay = backoff_base * (2**attempt)
                _LOGGER.warning(
                    "auto-resync attempt %d failed: %s; retrying in %.3fs",
                    attempt + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    async def close(self) -> None:
        self._closed = True
        self._trigger.set()

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            _LOGGER.info("auto-resync coordinator stopped")
