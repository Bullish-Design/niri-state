from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from niri_pypc import NiriConfig

from niri_state._core.models.health import HealthState
from niri_state._runtime.bootstrap import BootstrapOutcome, run_bootstrap
from niri_state.config import NiriStateConfig
from niri_state.errors import BootstrapError


def _output_dict(name: str) -> dict:
    return {
        "name": name,
        "make": "Dell",
        "model": "U2720Q",
        "serial": None,
        "physical_size": None,
        "modes": [],
        "current_mode": None,
        "is_custom_mode": False,
        "logical": None,
        "vrr_supported": False,
        "vrr_enabled": False,
    }


def _layout_dict() -> dict:
    return {
        "pos_in_scrolling_layout": None,
        "tile_pos_in_workspace_view": None,
        "tile_size": [],
        "window_offset_in_tile": [],
        "window_size": [],
        "position": None,
        "size": None,
    }


def _response_frame(response_dict: dict) -> bytes:
    return json.dumps(response_dict).encode() + b"\n"


def _make_output_response(name: str) -> bytes:
    return _response_frame({"Ok": {"Outputs": {name: _output_dict(name)}}})


def _make_workspaces_response(ws_list: list[dict]) -> bytes:
    return _response_frame({"Ok": {"Workspaces": ws_list}})


def _make_windows_response(win_list: list[dict]) -> bytes:
    for win in win_list:
        win["layout"] = _layout_dict()
    return _response_frame({"Ok": {"Windows": win_list}})


def _make_focused_output_response(name: str | None) -> bytes:
    if name is None:
        return _response_frame({"Ok": {"FocusedOutput": None}})
    return _response_frame({"Ok": {"FocusedOutput": _output_dict(name)}})


def _make_focused_window_response(win_id: int | None) -> bytes:
    if win_id is None:
        return _response_frame({"Ok": {"FocusedWindow": None}})
    return _response_frame(
        {
            "Ok": {
                "FocusedWindow": {
                    "id": win_id,
                    "app_id": "test",
                    "title": "Test",
                    "workspace_id": 1,
                    "is_focused": True,
                    "is_floating": False,
                    "is_urgent": False,
                    "pid": None,
                    "focus_timestamp": None,
                    "layout": _layout_dict(),
                }
            }
        }
    )


def _make_keyboard_response() -> bytes:
    return _response_frame({"Ok": {"KeyboardLayouts": {"current_idx": 0, "names": ["us"]}}})


def _make_overview_response(is_open: bool) -> bytes:
    return _response_frame({"Ok": {"OverviewState": {"is_open": is_open}}})


def _make_version_response(version: str) -> bytes:
    return _response_frame({"Ok": {"Version": version}})


async def _start_mock_server(
    socket_path: Path,
    cmd_responses: list[bytes],
    event_frames: list[dict],
) -> asyncio.Server:
    cmd_idx = [0]
    event_sent = [False]

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=5.0)
        except (TimeoutError, asyncio.IncompleteReadError):
            writer.close()
            return

        if not event_sent[0] and b"EventStream" in data:
            event_sent[0] = True
            for evt in event_frames:
                frame = json.dumps(evt).encode() + b"\n"
                writer.write(frame)
                await writer.drain()
                await asyncio.sleep(0.01)
            writer.close()
            await writer.wait_closed()
        else:
            if cmd_idx[0] < len(cmd_responses):
                writer.write(cmd_responses[cmd_idx[0]])
                await writer.drain()
                cmd_idx[0] += 1
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handler, path=str(socket_path))
    return server


class TestRunBootstrap:
    async def test_happy_path(self) -> None:
        cmd_responses = [
            _make_output_response("DP-1"),
            _make_workspaces_response(
                [
                    {
                        "id": 1,
                        "idx": 0,
                        "name": None,
                        "output": "DP-1",
                        "is_active": True,
                        "is_focused": True,
                        "is_urgent": False,
                        "active_window_id": None,
                    }
                ]
            ),
            _make_windows_response(
                [
                    {
                        "id": 100,
                        "app_id": "kitty",
                        "title": "Terminal",
                        "workspace_id": 1,
                        "is_focused": True,
                        "is_floating": False,
                        "is_urgent": False,
                        "pid": 1234,
                        "focus_timestamp": None,
                    }
                ]
            ),
            _make_focused_output_response("DP-1"),
            _make_focused_window_response(100),
            _make_keyboard_response(),
            _make_overview_response(False),
            _make_version_response("0.42.0"),
        ]

        tmpdir = tempfile.mkdtemp()
        try:
            socket_path = Path(tmpdir) / "test.sock"
            server = await _start_mock_server(socket_path, cmd_responses, [])

            config = NiriStateConfig(pypc=NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0))
            outcome: BootstrapOutcome | None = None
            try:
                outcome = await run_bootstrap(config)
                assert isinstance(outcome, BootstrapOutcome)
                assert outcome.initial_snapshot.revision == 1
                assert outcome.initial_snapshot.health == HealthState.LIVE
                assert "DP-1" in outcome.initial_snapshot.outputs
                assert 1 in outcome.initial_snapshot.workspaces
                assert 100 in outcome.initial_snapshot.windows
                assert outcome.initial_changeset.cause.value == "bootstrap"
            finally:
                server.close()
                await server.wait_closed()
                if outcome is not None:
                    await outcome.bundle.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def test_outputs_type_mismatch(self) -> None:
        cmd_responses = [_response_frame({"Ok": {"Outputs": "not-a-dict"}})]
        tmpdir = tempfile.mkdtemp()
        try:
            socket_path = Path(tmpdir) / "test.sock"
            server = await _start_mock_server(socket_path, cmd_responses, [])

            config = NiriStateConfig(pypc=NiriConfig(socket_path=socket_path, connect_timeout=2.0, request_timeout=2.0))
            try:
                with pytest.raises(BootstrapError):
                    await run_bootstrap(config)
            finally:
                server.close()
                await server.wait_closed()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def test_no_live_before_replay(self) -> None:
        cmd_responses = [
            _make_output_response("DP-1"),
            _make_workspaces_response(
                [
                    {
                        "id": 1,
                        "idx": 0,
                        "name": None,
                        "output": "DP-1",
                        "is_active": True,
                        "is_focused": False,
                        "is_urgent": False,
                        "active_window_id": None,
                    }
                ]
            ),
            _make_windows_response([]),
            _make_focused_output_response("DP-1"),
            _make_focused_window_response(None),
            _make_keyboard_response(),
            _make_overview_response(False),
            _make_version_response("0.42.0"),
        ]

        tmpdir = tempfile.mkdtemp()
        try:
            socket_path = Path(tmpdir) / "test.sock"
            server = await _start_mock_server(socket_path, cmd_responses, [])

            config = NiriStateConfig(pypc=NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0))
            outcome: BootstrapOutcome | None = None
            try:
                outcome = await run_bootstrap(config)
                assert outcome.initial_snapshot.health == HealthState.LIVE
                assert outcome.initial_snapshot.revision == 1
            finally:
                server.close()
                await server.wait_closed()
                if outcome is not None:
                    await outcome.bundle.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def test_version_optional(self) -> None:
        cmd_responses = [
            _make_output_response("DP-1"),
            _make_workspaces_response([]),
            _make_windows_response([]),
            _make_focused_output_response("DP-1"),
            _make_focused_window_response(None),
            _make_keyboard_response(),
            _make_overview_response(False),
        ]

        tmpdir = tempfile.mkdtemp()
        try:
            socket_path = Path(tmpdir) / "test.sock"
            server = await _start_mock_server(socket_path, cmd_responses, [])

            config = NiriStateConfig(pypc=NiriConfig(socket_path=socket_path, connect_timeout=5.0, request_timeout=5.0))
            outcome: BootstrapOutcome | None = None
            try:
                outcome = await run_bootstrap(config)
                assert outcome.initial_snapshot.compatibility.compositor_version is None
            finally:
                server.close()
                await server.wait_closed()
                if outcome is not None:
                    await outcome.bundle.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
