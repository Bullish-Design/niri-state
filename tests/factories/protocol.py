from __future__ import annotations

from pydantic import TypeAdapter

from niri_state.protocol import (
    KeyboardLayouts,
    LogicalOutput,
    Mode,
    Output,
    Overview,
    Timestamp,
    Window,
    WindowLayout,
    Workspace,
)

_OUTPUT_ADAPTER = TypeAdapter(Output)
_WORKSPACE_ADAPTER = TypeAdapter(Workspace)
_WINDOW_ADAPTER = TypeAdapter(Window)
_KEYBOARD_ADAPTER = TypeAdapter(KeyboardLayouts)
_OVERVIEW_ADAPTER = TypeAdapter(Overview)
_TIMESTAMP_ADAPTER = TypeAdapter(Timestamp)
_WINDOW_LAYOUT_ADAPTER = TypeAdapter(WindowLayout)
_MODE_ADAPTER = TypeAdapter(Mode)
_LOGICAL_OUTPUT_ADAPTER = TypeAdapter(LogicalOutput)


def make_timestamp(**overrides: object) -> Timestamp:
    payload = {
        "secs": 1,
        "nanos": 0,
    }
    payload.update(overrides)
    return _TIMESTAMP_ADAPTER.validate_python(payload)


def make_window_layout(**overrides: object) -> WindowLayout:
    payload = {
        "tile_size": [800.0, 600.0],
        "window_size": [800, 600],
        "window_offset_in_tile": [0.0, 0.0],
        "tile_pos_in_workspace_view": [0.0, 0.0],
        "pos_in_scrolling_layout": [0, 0],
    }
    payload.update(overrides)
    return _WINDOW_LAYOUT_ADAPTER.validate_python(payload)


def make_mode(**overrides: object) -> Mode:
    payload = {
        "width": 3840,
        "height": 2160,
        "refresh_rate": 60000,
        "is_preferred": True,
    }
    payload.update(overrides)
    return _MODE_ADAPTER.validate_python(payload)


def make_logical_output(**overrides: object) -> LogicalOutput:
    payload = {
        "x": 0,
        "y": 0,
        "width": 3840,
        "height": 2160,
        "scale": 1.0,
        "transform": "Normal",
    }
    payload.update(overrides)
    return _LOGICAL_OUTPUT_ADAPTER.validate_python(payload)


def make_output(**overrides: object) -> Output:
    payload = {
        "name": "HDMI-A-1",
        "make": "Dell",
        "model": "U2720Q",
        "serial": None,
        "physical_size": None,
        "modes": [make_mode()],
        "current_mode": 0,
        "logical": make_logical_output(),
        "is_custom_mode": False,
        "vrr_supported": False,
        "vrr_enabled": False,
    }
    payload.update(overrides)
    return _OUTPUT_ADAPTER.validate_python(payload)


def make_workspace(**overrides: object) -> Workspace:
    payload = {
        "id": 1,
        "idx": 1,
        "name": None,
        "output": "HDMI-A-1",
        "is_active": True,
        "is_focused": True,
        "is_urgent": False,
        "active_window_id": None,
    }
    payload.update(overrides)
    return _WORKSPACE_ADAPTER.validate_python(payload)


def make_window(**overrides: object) -> Window:
    payload = {
        "id": 100,
        "title": "Terminal",
        "app_id": "foot",
        "pid": None,
        "workspace_id": 1,
        "is_focused": False,
        "is_floating": False,
        "is_urgent": False,
        "focus_timestamp": make_timestamp(),
        "layout": make_window_layout(),
    }
    payload.update(overrides)
    return _WINDOW_ADAPTER.validate_python(payload)


def make_keyboard_layouts(**overrides: object) -> KeyboardLayouts:
    payload = {
        "names": ["US", "DE"],
        "current_idx": 0,
    }
    payload.update(overrides)
    return _KEYBOARD_ADAPTER.validate_python(payload)


def make_overview(**overrides: object) -> Overview:
    payload = {
        "is_open": False,
    }
    payload.update(overrides)
    return _OVERVIEW_ADAPTER.validate_python(payload)
