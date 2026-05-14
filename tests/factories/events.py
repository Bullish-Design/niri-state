from __future__ import annotations

from niri_state.adapters.protocol import (
    ConfigLoadedEvent,
    EventValue,
    KeyboardLayoutsChangedEvent,
    KeyboardLayoutSwitchedEvent,
    OverviewOpenedOrClosedEvent,
    WindowClosedEvent,
    WindowFocusChangedEvent,
    WindowFocusTimestampChangedEvent,
    WindowLayoutsChangedEvent,
    WindowOpenedOrChangedEvent,
    WindowsChangedEvent,
    WindowUrgencyChangedEvent,
    WorkspaceActivatedEvent,
    WorkspaceActiveWindowChangedEvent,
    WorkspacesChangedEvent,
    WorkspaceUrgencyChangedEvent,
)
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_timestamp,
    make_window,
    make_window_layout,
    make_workspace,
)


def make_windows_changed_event(**overrides: object) -> WindowsChangedEvent:
    payload = {"windows": [make_window()]}
    payload.update(overrides)
    return WindowsChangedEvent.model_validate(payload)


def make_window_opened_or_changed_event(**overrides: object) -> WindowOpenedOrChangedEvent:
    payload = {"window": make_window()}
    payload.update(overrides)
    return WindowOpenedOrChangedEvent.model_validate(payload)


def make_window_closed_event(**overrides: object) -> WindowClosedEvent:
    payload = {"id": 100}
    payload.update(overrides)
    return WindowClosedEvent.model_validate(payload)


def make_window_focus_changed_event(**overrides: object) -> WindowFocusChangedEvent:
    payload = {"id": 100}
    payload.update(overrides)
    return WindowFocusChangedEvent.model_validate(payload)


def make_window_urgency_changed_event(**overrides: object) -> WindowUrgencyChangedEvent:
    payload = {"id": 100, "urgent": True}
    payload.update(overrides)
    return WindowUrgencyChangedEvent.model_validate(payload)


def make_window_focus_timestamp_changed_event(
    **overrides: object,
) -> WindowFocusTimestampChangedEvent:
    payload = {"id": 100, "focus_timestamp": make_timestamp()}
    payload.update(overrides)
    return WindowFocusTimestampChangedEvent.model_validate(payload)


def make_window_layouts_changed_event(**overrides: object) -> WindowLayoutsChangedEvent:
    payload = {"changes": [(100, make_window_layout())]}
    payload.update(overrides)
    return WindowLayoutsChangedEvent.model_validate(payload)


def make_workspaces_changed_event(**overrides: object) -> WorkspacesChangedEvent:
    payload = {"workspaces": [make_workspace()]}
    payload.update(overrides)
    return WorkspacesChangedEvent.model_validate(payload)


def make_workspace_activated_event(**overrides: object) -> WorkspaceActivatedEvent:
    payload = {"id": 1, "focused": True}
    payload.update(overrides)
    return WorkspaceActivatedEvent.model_validate(payload)


def make_workspace_active_window_changed_event(
    **overrides: object,
) -> WorkspaceActiveWindowChangedEvent:
    payload = {"workspace_id": 1, "active_window_id": 100}
    payload.update(overrides)
    return WorkspaceActiveWindowChangedEvent.model_validate(payload)


def make_workspace_urgency_changed_event(**overrides: object) -> WorkspaceUrgencyChangedEvent:
    payload = {"id": 1, "urgent": True}
    payload.update(overrides)
    return WorkspaceUrgencyChangedEvent.model_validate(payload)


def make_keyboard_layouts_changed_event(**overrides: object) -> KeyboardLayoutsChangedEvent:
    payload = {"keyboard_layouts": make_keyboard_layouts()}
    payload.update(overrides)
    return KeyboardLayoutsChangedEvent.model_validate(payload)


def make_keyboard_layout_switched_event(**overrides: object) -> KeyboardLayoutSwitchedEvent:
    payload = {"idx": 0}
    payload.update(overrides)
    return KeyboardLayoutSwitchedEvent.model_validate(payload)


def make_overview_opened_or_closed_event(
    **overrides: object,
) -> OverviewOpenedOrClosedEvent:
    payload = {"is_open": False}
    payload.update(overrides)
    return OverviewOpenedOrClosedEvent.model_validate(payload)


def make_config_loaded_event(**overrides: object) -> ConfigLoadedEvent:
    payload = {"failed": False}
    payload.update(overrides)
    return ConfigLoadedEvent.model_validate(payload)


def make_event_sequence() -> tuple[EventValue, ...]:
    return (
        make_workspaces_changed_event(),
        make_windows_changed_event(),
        make_window_focus_changed_event(),
        make_keyboard_layouts_changed_event(),
    )
