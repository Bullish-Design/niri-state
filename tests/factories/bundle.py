from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from niri_state.adapters.protocol import (
    FocusedOutputRequest,
    FocusedOutputResponse,
    FocusedWindowRequest,
    FocusedWindowResponse,
    KeyboardLayoutsRequest,
    KeyboardLayoutsResponse,
    NiriConnectionBundle,
    OutputsRequest,
    OutputsResponse,
    OverviewStateRequest,
    OverviewStateResponse,
    VersionRequest,
    VersionResponse,
    WindowsRequest,
    WindowsResponse,
    WorkspacesRequest,
    WorkspacesResponse,
)
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_output,
    make_overview,
    make_window,
    make_workspace,
)


class FakeClient:
    def __init__(
        self,
        *,
        outputs: dict[str, object] | None = None,
        workspaces: list[object] | None = None,
        windows: list[object] | None = None,
        focused_output: object | None = None,
        focused_window: object | None = None,
        keyboard_layouts: object | None = None,
        overview: object | None = None,
        version: str = "25.11",
    ) -> None:
        self.outputs = outputs or {"HDMI-A-1": make_output()}
        self.workspaces = workspaces or [make_workspace()]
        self.windows = windows or [make_window()]
        self.focused_output = focused_output if focused_output is not None else make_output()
        self.focused_window = focused_window if focused_window is not None else make_window()
        self.keyboard_layouts = keyboard_layouts if keyboard_layouts is not None else make_keyboard_layouts()
        self.overview = overview if overview is not None else make_overview()
        self.version = version

    async def request(self, req: object):
        if isinstance(req, OutputsRequest):
            return OutputsResponse(payload=self.outputs)
        if isinstance(req, WorkspacesRequest):
            return WorkspacesResponse(payload=self.workspaces)
        if isinstance(req, WindowsRequest):
            return WindowsResponse(payload=self.windows)
        if isinstance(req, FocusedWindowRequest):
            return FocusedWindowResponse(payload=self.focused_window)
        if isinstance(req, FocusedOutputRequest):
            return FocusedOutputResponse(payload=self.focused_output)
        if isinstance(req, KeyboardLayoutsRequest):
            return KeyboardLayoutsResponse(payload=self.keyboard_layouts)
        if isinstance(req, OverviewStateRequest):
            return OverviewStateResponse(payload=self.overview)
        if isinstance(req, VersionRequest):
            return VersionResponse(payload=self.version)
        msg = f"unexpected request: {type(req).__name__}"
        raise AssertionError(msg)

    async def close(self) -> None:
        return None


class FakeEventStream:
    def __init__(self, events: tuple[object, ...], *, delay_s: float = 0.0) -> None:
        self._events = events
        self._delay_s = delay_s
        self._closed = False

    def __aiter__(self) -> AsyncIterator[object]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[object]:
        for event in self._events:
            if self._closed:
                break
            if self._delay_s > 0:
                await asyncio.sleep(self._delay_s)
            yield event

    async def close(self) -> None:
        self._closed = True


class FakeBundle(NiriConnectionBundle):
    def __init__(
        self,
        *,
        events: tuple[object, ...] = (),
        client: FakeClient | None = None,
        event_delay_s: float = 0.0,
    ) -> None:
        super().__init__(client or FakeClient(), FakeEventStream(events, delay_s=event_delay_s))
