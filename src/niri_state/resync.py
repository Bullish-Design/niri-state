from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from niri_state.changes import ChangeCause
from niri_state.config import NiriStateConfig, ResyncPolicy

if TYPE_CHECKING:
    from niri_state.store import NiriState


class ResyncCoordinator:
    def __init__(self, state: NiriState, config: NiriStateConfig) -> None:
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
        self._task = asyncio.create_task(self._run())

    def request(self) -> None:
        if self._closed:
            return
        self._trigger.set()

    async def _run(self) -> None:
        while not self._closed:
            await self._trigger.wait()
            self._trigger.clear()

            if self._closed:
                return

            try:
                await self._state.refresh(cause=ChangeCause.RESYNC)
            except asyncio.CancelledError:
                raise
            except Exception:
                continue

    async def close(self) -> None:
        self._closed = True
        self._trigger.set()

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
