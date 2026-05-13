from __future__ import annotations

from collections.abc import AsyncIterator

from niri_state.protocol import (
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
    async def request(self, req: object):
        if isinstance(req, OutputsRequest):
            return OutputsResponse(payload={"HDMI-A-1": make_output()})
        if isinstance(req, WorkspacesRequest):
            return WorkspacesResponse(payload=[make_workspace()])
        if isinstance(req, WindowsRequest):
            return WindowsResponse(payload=[make_window()])
        if isinstance(req, FocusedWindowRequest):
            return FocusedWindowResponse(payload=make_window())
        if isinstance(req, FocusedOutputRequest):
            return FocusedOutputResponse(payload=make_output())
        if isinstance(req, KeyboardLayoutsRequest):
            return KeyboardLayoutsResponse(payload=make_keyboard_layouts())
        if isinstance(req, OverviewStateRequest):
            return OverviewStateResponse(payload=make_overview())
        if isinstance(req, VersionRequest):
            return VersionResponse(payload="25.11")
        msg = f"unexpected request: {type(req).__name__}"
        raise AssertionError(msg)

    async def close(self) -> None:
        return None


class FakeEventStream:
    def __init__(self, events: tuple[object, ...]) -> None:
        self._events = events
        self._closed = False

    def __aiter__(self) -> AsyncIterator[object]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[object]:
        for event in self._events:
            if self._closed:
                break
            yield event

    async def close(self) -> None:
        self._closed = True


class FakeBundle(NiriConnectionBundle):
    def __init__(self, *, events: tuple[object, ...] = ()) -> None:
        super().__init__(FakeClient(), FakeEventStream(events))
