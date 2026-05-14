from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from niri_state.adapters.protocol import (
    ConfigLoadedEvent,
    EventValue,
    KeyboardLayoutsChangedEvent,
    KeyboardLayoutSwitchedEvent,
    OverviewOpenedOrClosedEvent,
    ScreenshotCapturedEvent,
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
from niri_state.api.changes import ChangedDomain
from niri_state.api.config import NiriStateConfig, UnknownEventPolicy
from niri_state.api.errors import DesyncError, ReductionError
from niri_state.core.diagnostics import with_desync, with_event_applied
from niri_state.core.engine_state import EngineState


@dataclass(frozen=True, slots=True)
class ReduceResult:
    applied: bool
    domains: frozenset[ChangedDomain]
    marked_desync: bool = False


Reducer = Callable[[EngineState, object], frozenset[ChangedDomain]]
EVENT_REDUCERS: dict[type[EventValue], Reducer] = {}


def register(event_type: type[EventValue]) -> Callable[[Reducer], Reducer]:
    def decorator(fn: Reducer) -> Reducer:
        EVENT_REDUCERS[event_type] = fn
        return fn

    return decorator


def reduce_event(
    engine: EngineState,
    event: EventValue,
    *,
    config: NiriStateConfig,
    revision: int,
) -> ReduceResult:
    event_type = type(event).__name__
    engine.diagnostics = with_event_applied(engine.diagnostics, event_type=event_type)

    reducer = EVENT_REDUCERS.get(type(event))
    if reducer is None:
        return _handle_unknown_event(
            engine,
            event,
            config=config,
            revision=revision,
        )

    try:
        domains = reducer(engine, event)
        return ReduceResult(applied=True, domains=domains)
    except DesyncError:
        raise
    except Exception as exc:
        raise ReductionError(
            f"failed reducing event {event_type}",
            event_type=event_type,
            revision=revision,
            operation="reduce_event",
            cause=exc,
        ) from exc


@register(WindowsChangedEvent)
def reduce_windows_changed(
    engine: EngineState,
    event: WindowsChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.windows = {window.id: window for window in event.windows}
    return frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})


@register(WindowOpenedOrChangedEvent)
def reduce_window_opened_or_changed(
    engine: EngineState,
    event: WindowOpenedOrChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.windows[event.window.id] = event.window

    domains = {ChangedDomain.WINDOWS}
    if event.window.is_focused:
        engine.focused_window_id = event.window.id
        domains.add(ChangedDomain.FOCUS)

    return frozenset(domains)


@register(WindowClosedEvent)
def reduce_window_closed(
    engine: EngineState,
    event: WindowClosedEvent,
) -> frozenset[ChangedDomain]:
    engine.windows.pop(event.id, None)

    if engine.focused_window_id == event.id:
        engine.focused_window_id = None
        return frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})

    return frozenset({ChangedDomain.WINDOWS})


@register(WindowFocusChangedEvent)
def reduce_window_focus_changed(
    engine: EngineState,
    event: WindowFocusChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.focused_window_id = event.id
    return frozenset({ChangedDomain.FOCUS})


@register(WindowUrgencyChangedEvent)
def reduce_window_urgency_changed(
    engine: EngineState,
    event: WindowUrgencyChangedEvent,
) -> frozenset[ChangedDomain]:
    window = engine.windows.get(event.id)
    if window is None:
        raise DesyncError(
            "window urgency changed for unknown window",
            event_type=type(event).__name__,
            operation="reduce_window_urgency_changed",
        )

    engine.windows[event.id] = window.model_copy(update={"is_urgent": event.urgent})
    return frozenset({ChangedDomain.WINDOWS})


@register(WindowFocusTimestampChangedEvent)
def reduce_window_focus_timestamp_changed(
    engine: EngineState,
    event: WindowFocusTimestampChangedEvent,
) -> frozenset[ChangedDomain]:
    window = engine.windows.get(event.id)
    if window is None:
        raise DesyncError(
            "window focus timestamp changed for unknown window",
            event_type=type(event).__name__,
            operation="reduce_window_focus_timestamp_changed",
        )

    engine.windows[event.id] = window.model_copy(update={"focus_timestamp": event.focus_timestamp})
    return frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})


@register(WindowLayoutsChangedEvent)
def reduce_window_layouts_changed(
    engine: EngineState,
    event: WindowLayoutsChangedEvent,
) -> frozenset[ChangedDomain]:
    for window_id, layout in event.changes:
        window = engine.windows.get(window_id)
        if window is None:
            raise DesyncError(
                "window layout changed for unknown window",
                event_type=type(event).__name__,
                operation="reduce_window_layouts_changed",
            )
        engine.windows[window_id] = window.model_copy(update={"layout": layout})
    return frozenset({ChangedDomain.WINDOWS})


@register(WorkspacesChangedEvent)
def reduce_workspaces_changed(
    engine: EngineState,
    event: WorkspacesChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.workspaces = {workspace.id: workspace for workspace in event.workspaces}
    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})


@register(WorkspaceActivatedEvent)
def reduce_workspace_activated(
    engine: EngineState,
    event: WorkspaceActivatedEvent,
) -> frozenset[ChangedDomain]:
    workspace = engine.workspaces.get(event.id)
    if workspace is None:
        raise DesyncError(
            "workspace activated for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_activated",
        )

    updated: dict[int, object] = {}
    for workspace_id, existing in engine.workspaces.items():
        if existing.output != workspace.output:
            continue
        if existing.is_active or existing.is_focused:
            updated[workspace_id] = existing.model_copy(update={"is_active": False, "is_focused": False})

    engine.workspaces.update(updated)
    is_focused = event.focused
    engine.workspaces[event.id] = workspace.model_copy(update={"is_active": True, "is_focused": is_focused})
    engine.focused_workspace_id = event.id if is_focused else engine.focused_workspace_id

    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})


@register(WorkspaceActiveWindowChangedEvent)
def reduce_workspace_active_window_changed(
    engine: EngineState,
    event: WorkspaceActiveWindowChangedEvent,
) -> frozenset[ChangedDomain]:
    workspace = engine.workspaces.get(event.workspace_id)
    if workspace is None:
        raise DesyncError(
            "workspace active window changed for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_active_window_changed",
        )

    engine.workspaces[event.workspace_id] = workspace.model_copy(update={"active_window_id": event.active_window_id})
    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})


@register(WorkspaceUrgencyChangedEvent)
def reduce_workspace_urgency_changed(
    engine: EngineState,
    event: WorkspaceUrgencyChangedEvent,
) -> frozenset[ChangedDomain]:
    workspace = engine.workspaces.get(event.id)
    if workspace is None:
        raise DesyncError(
            "workspace urgency changed for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_urgency_changed",
        )

    engine.workspaces[event.id] = workspace.model_copy(update={"is_urgent": event.urgent})
    return frozenset({ChangedDomain.WORKSPACES})


@register(KeyboardLayoutsChangedEvent)
def reduce_keyboard_layouts_changed(
    engine: EngineState,
    event: KeyboardLayoutsChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.keyboard_layouts = event.keyboard_layouts
    return frozenset({ChangedDomain.KEYBOARD})


@register(KeyboardLayoutSwitchedEvent)
def reduce_keyboard_layout_switched(
    engine: EngineState,
    event: KeyboardLayoutSwitchedEvent,
) -> frozenset[ChangedDomain]:
    current = engine.keyboard_layouts
    if current is None:
        raise DesyncError(
            "keyboard layout switched before keyboard state initialized",
            event_type=type(event).__name__,
            operation="reduce_keyboard_layout_switched",
        )

    update = cast(Mapping[str, Any], {"current_idx": event.idx})
    engine.keyboard_layouts = current.model_copy(update=update)
    return frozenset({ChangedDomain.KEYBOARD})


@register(OverviewOpenedOrClosedEvent)
def reduce_overview_opened_or_closed(
    engine: EngineState,
    event: OverviewOpenedOrClosedEvent,
) -> frozenset[ChangedDomain]:
    current = engine.overview
    if current is None:
        raise DesyncError(
            "overview changed before overview state initialized",
            event_type=type(event).__name__,
            operation="reduce_overview_opened_or_closed",
        )

    update = cast(Mapping[str, Any], {"is_open": event.is_open})
    engine.overview = current.model_copy(update=update)
    return frozenset({ChangedDomain.OVERVIEW})


@register(ConfigLoadedEvent)
def reduce_config_loaded(
    engine: EngineState,
    event: ConfigLoadedEvent,
) -> frozenset[ChangedDomain]:
    return frozenset()


@register(ScreenshotCapturedEvent)
def reduce_screenshot_captured(
    engine: EngineState,
    event: ScreenshotCapturedEvent,
) -> frozenset[ChangedDomain]:
    return frozenset()


def _handle_unknown_event(
    engine: EngineState,
    event: EventValue,
    *,
    config: NiriStateConfig,
    revision: int,
) -> ReduceResult:
    event_type = type(event).__name__
    policy = config.unknown_event_policy

    if policy is UnknownEventPolicy.IGNORE:
        return ReduceResult(applied=False, domains=frozenset())

    if policy is UnknownEventPolicy.STALE:
        engine.diagnostics = with_desync(
            engine.diagnostics,
            event_type=event_type,
            reason="unknown event",
        )
        return ReduceResult(
            applied=True,
            domains=frozenset({ChangedDomain.DIAGNOSTICS}),
            marked_desync=True,
        )

    raise DesyncError(
        "unknown event encountered",
        event_type=event_type,
        revision=revision,
        operation="unknown_event",
    )
