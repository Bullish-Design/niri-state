from __future__ import annotations

from niri_pypc.types.generated.event import (
    ConfigLoadedEvent,
    KeyboardLayoutsChangedEvent,
    KeyboardLayoutSwitchedEvent,
    OverviewOpenedOrClosedEvent,
    ScreenshotCapturedEvent,
    UnknownEvent,
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
from pydantic import BaseModel, ConfigDict

from niri_state._core.models.changes import ChangeCause, ChangedDomain
from niri_state._core.models.draft import DraftState
from niri_state._core.reducers import keyboard, overview, windows, workspaces
from niri_state.config import UnknownEventPolicy


class ReduceResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    applied: bool
    changed_domains: frozenset[ChangedDomain]
    cause: ChangeCause
    event_type: str | None = None
    event_summary: str | None = None


def reduce_event(
    draft: DraftState,
    event: object,
    unknown_event_policy: UnknownEventPolicy | str,
) -> ReduceResult:
    """Dispatch on concrete event class and apply appropriate reducer."""
    policy = _normalize_unknown_event_policy(unknown_event_policy)
    changed_domains: set[ChangedDomain] = set()

    match event:
        case WindowsChangedEvent() as e:
            changed = windows.apply_windows_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WINDOWS)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WindowsChangedEvent",
            )

        case WindowOpenedOrChangedEvent() as e:
            changed = windows.apply_window_opened_or_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WINDOWS)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WindowOpenedOrChangedEvent",
            )

        case WindowClosedEvent() as e:
            changed = windows.apply_window_closed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WINDOWS)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WindowClosedEvent",
            )

        case WindowFocusChangedEvent() as e:
            changed = windows.apply_window_focus_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WINDOWS)
                changed_domains.add(ChangedDomain.FOCUS)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WindowFocusChangedEvent",
            )

        case WindowUrgencyChangedEvent() as e:
            changed = windows.apply_window_urgency_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WINDOWS)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WindowUrgencyChangedEvent",
            )

        case WindowFocusTimestampChangedEvent() as e:
            changed = windows.apply_window_focus_timestamp_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WINDOWS)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WindowFocusTimestampChangedEvent",
            )

        case WindowLayoutsChangedEvent() as e:
            changed = windows.apply_window_layouts_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WINDOWS)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WindowLayoutsChangedEvent",
            )

        case WorkspacesChangedEvent() as e:
            changed = workspaces.apply_workspaces_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WORKSPACES)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WorkspacesChangedEvent",
            )

        case WorkspaceActivatedEvent() as e:
            changed = workspaces.apply_workspace_activated(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WORKSPACES)
                changed_domains.add(ChangedDomain.FOCUS)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WorkspaceActivatedEvent",
            )

        case WorkspaceActiveWindowChangedEvent() as e:
            changed = workspaces.apply_workspace_active_window_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WORKSPACES)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WorkspaceActiveWindowChangedEvent",
            )

        case WorkspaceUrgencyChangedEvent() as e:
            changed = workspaces.apply_workspace_urgency_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.WORKSPACES)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="WorkspaceUrgencyChangedEvent",
            )

        case KeyboardLayoutsChangedEvent() as e:
            changed = keyboard.apply_keyboard_layouts_changed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.KEYBOARD)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="KeyboardLayoutsChangedEvent",
            )

        case KeyboardLayoutSwitchedEvent() as e:
            changed = keyboard.apply_keyboard_layout_switched(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.KEYBOARD)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="KeyboardLayoutSwitchedEvent",
            )

        case OverviewOpenedOrClosedEvent() as e:
            changed = overview.apply_overview_opened_or_closed(draft, e)
            if changed:
                changed_domains.add(ChangedDomain.OVERVIEW)
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(changed_domains),
                cause=ChangeCause.EVENT,
                event_type="OverviewOpenedOrClosedEvent",
            )

        case ConfigLoadedEvent() as e:
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(),
                cause=ChangeCause.EVENT,
                event_type="ConfigLoadedEvent",
            )

        case ScreenshotCapturedEvent() as e:
            return ReduceResult(
                applied=True,
                changed_domains=frozenset(),
                cause=ChangeCause.EVENT,
                event_type="ScreenshotCapturedEvent",
            )

        case UnknownEvent() as e:
            return _handle_unknown_event(draft, e, policy)

        case _:
            return ReduceResult(
                applied=False,
                changed_domains=frozenset(),
                cause=ChangeCause.EVENT,
                event_type=None,
            )


def _handle_unknown_event(
    draft: DraftState,
    event: UnknownEvent,
    policy: UnknownEventPolicy,
) -> ReduceResult:
    """Handle unknown events according to policy."""
    from niri_state._core.models.health import HealthState
    from niri_state.errors import DesyncError

    variant_name = event.variant_name

    if policy is UnknownEventPolicy.STALE:
        draft.health = HealthState.STALE
        draft.diagnostics = draft.diagnostics.model_copy(
            update={"unknown_events_seen": draft.diagnostics.unknown_events_seen + 1}  # type: ignore[arg-type]
        )
        return ReduceResult(
            applied=True,
            changed_domains=frozenset({ChangedDomain.HEALTH}),
            cause=ChangeCause.EVENT,
            event_type=variant_name,
            event_summary="unknown event -> stale",
        )

    if policy is UnknownEventPolicy.FAIL:
        raise DesyncError(
            f"Unknown event type: {variant_name}",
            event_type=variant_name,
        )

    if policy is UnknownEventPolicy.IGNORE:
        return ReduceResult(
            applied=False,
            changed_domains=frozenset(),
            cause=ChangeCause.EVENT,
            event_type=variant_name,
            event_summary="unknown event ignored",
        )

    return ReduceResult(
        applied=False,
        changed_domains=frozenset(),
        cause=ChangeCause.EVENT,
        event_type=variant_name,
    )


def _normalize_unknown_event_policy(policy: UnknownEventPolicy | str) -> UnknownEventPolicy:
    if isinstance(policy, UnknownEventPolicy):
        return policy
    normalized = policy.strip().lower()
    if normalized == "stale":
        return UnknownEventPolicy.STALE
    if normalized == "fail":
        return UnknownEventPolicy.FAIL
    if normalized == "ignore":
        return UnknownEventPolicy.IGNORE
    return UnknownEventPolicy.STALE
