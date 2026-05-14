from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
from tests.factories.events import (
    make_config_loaded_event,
    make_keyboard_layout_switched_event,
    make_keyboard_layouts_changed_event,
    make_overview_opened_or_closed_event,
    make_window_closed_event,
    make_window_focus_changed_event,
    make_window_focus_timestamp_changed_event,
    make_window_layouts_changed_event,
    make_window_opened_or_changed_event,
    make_window_urgency_changed_event,
    make_workspace_activated_event,
    make_workspace_active_window_changed_event,
    make_workspace_urgency_changed_event,
    make_workspaces_changed_event,
)
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_overview,
    make_timestamp,
    make_window,
    make_workspace,
)

from niri_state.adapters.protocol import UnknownEvent
from niri_state.api.changes import ChangedDomain
from niri_state.api.config import NiriStateConfig, UnknownEventPolicy
from niri_state.api.errors import DesyncError
from niri_state.api.health import HealthState
from niri_state.core.engine_state import EngineState
from niri_state.core.reducers import (
    reduce_config_loaded,
    reduce_event,
    reduce_keyboard_layout_switched,
    reduce_keyboard_layouts_changed,
    reduce_overview_opened_or_closed,
    reduce_window_closed,
    reduce_window_focus_changed,
    reduce_window_focus_timestamp_changed,
    reduce_window_layouts_changed,
    reduce_window_opened_or_changed,
    reduce_window_urgency_changed,
    reduce_windows_changed,
    reduce_workspace_activated,
    reduce_workspace_active_window_changed,
    reduce_workspace_urgency_changed,
    reduce_workspaces_changed,
)


class _WindowsChangedEventStub:
    def __init__(self, windows):
        self.windows = windows


def test_reduce_windows_changed_replaces_windows() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()

    event = _WindowsChangedEventStub(windows=[make_window(id=100), make_window(id=101)])
    domains = reduce_windows_changed(engine, event)

    assert set(engine.windows) == {100, 101}
    assert domains == frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})


def test_reduce_window_urgency_changed_uses_urgent_field() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.windows = {100: make_window(id=100, is_urgent=False)}

    domains = reduce_window_urgency_changed(
        engine,
        make_window_urgency_changed_event(id=100, urgent=True),
    )

    assert domains == frozenset({ChangedDomain.WINDOWS})
    assert engine.windows[100].is_urgent is True


def test_reduce_window_layouts_changed_consumes_changes_list() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    old_layout = make_window(id=100).layout
    update = cast(Mapping[str, Any], {"window_size": [1024, 768]})
    new_layout = old_layout.model_copy(update=update)
    engine.windows = {100: make_window(id=100, layout=old_layout)}

    domains = reduce_window_layouts_changed(
        engine,
        make_window_layouts_changed_event(changes=[(100, new_layout)]),
    )

    assert domains == frozenset({ChangedDomain.WINDOWS})
    assert engine.windows[100].layout.window_size == [1024, 768]


def test_reduce_workspace_activated_honors_focused_flag() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.workspaces = {
        1: make_workspace(id=1, output="HDMI-A-1", is_active=True, is_focused=True),
        2: make_workspace(id=2, output="HDMI-A-1", is_active=False, is_focused=False),
    }

    domains = reduce_workspace_activated(
        engine,
        make_workspace_activated_event(id=2, focused=False),
    )

    assert domains == frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})
    assert engine.workspaces[2].is_active is True
    assert engine.workspaces[2].is_focused is False


def _engine_with_defaults() -> EngineState:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.workspaces = {1: make_workspace(id=1, output="HDMI-A-1")}
    engine.windows = {100: make_window(id=100, workspace_id=1)}
    return engine


def test_reduce_window_opened_or_changed_adds_new_window() -> None:
    engine = _engine_with_defaults()
    event = make_window_opened_or_changed_event(window=make_window(id=200, workspace_id=1))
    domains = reduce_window_opened_or_changed(engine, event)

    assert 200 in engine.windows
    assert ChangedDomain.WINDOWS in domains


def test_reduce_window_opened_or_changed_updates_focus_when_focused() -> None:
    engine = _engine_with_defaults()
    event = make_window_opened_or_changed_event(window=make_window(id=200, workspace_id=1, is_focused=True))
    domains = reduce_window_opened_or_changed(engine, event)

    assert engine.focused_window_id == 200
    assert ChangedDomain.FOCUS in domains


def test_reduce_window_closed_removes_window() -> None:
    engine = _engine_with_defaults()
    event = make_window_closed_event(id=100)
    domains = reduce_window_closed(engine, event)

    assert 100 not in engine.windows
    assert ChangedDomain.WINDOWS in domains


def test_reduce_window_closed_clears_focus_if_focused() -> None:
    engine = _engine_with_defaults()
    engine.focused_window_id = 100
    event = make_window_closed_event(id=100)
    domains = reduce_window_closed(engine, event)

    assert engine.focused_window_id is None
    assert ChangedDomain.FOCUS in domains


def test_reduce_window_focus_changed_sets_focus() -> None:
    engine = _engine_with_defaults()
    event = make_window_focus_changed_event(id=100)
    domains = reduce_window_focus_changed(engine, event)

    assert engine.focused_window_id == 100
    assert domains == frozenset({ChangedDomain.FOCUS})


def test_reduce_window_focus_timestamp_changed_updates_timestamp() -> None:
    engine = _engine_with_defaults()
    new_ts = make_timestamp(secs=42)
    event = make_window_focus_timestamp_changed_event(id=100, focus_timestamp=new_ts)
    domains = reduce_window_focus_timestamp_changed(engine, event)

    assert engine.windows[100].focus_timestamp.secs == 42
    assert ChangedDomain.FOCUS in domains


def test_reduce_window_focus_timestamp_changed_raises_on_unknown_window() -> None:
    engine = _engine_with_defaults()
    event = make_window_focus_timestamp_changed_event(id=999)
    with pytest.raises(DesyncError):
        reduce_window_focus_timestamp_changed(engine, event)


def test_reduce_workspaces_changed_replaces_all() -> None:
    engine = _engine_with_defaults()
    new_ws = [make_workspace(id=5, output="DP-1"), make_workspace(id=6, output="DP-1")]
    event = make_workspaces_changed_event(workspaces=new_ws)
    domains = reduce_workspaces_changed(engine, event)

    assert set(engine.workspaces) == {5, 6}
    assert ChangedDomain.WORKSPACES in domains


def test_reduce_workspace_active_window_changed_updates_workspace() -> None:
    engine = _engine_with_defaults()
    event = make_workspace_active_window_changed_event(workspace_id=1, active_window_id=100)
    domains = reduce_workspace_active_window_changed(engine, event)

    assert engine.workspaces[1].active_window_id == 100
    assert ChangedDomain.WORKSPACES in domains


def test_reduce_workspace_active_window_changed_raises_on_unknown() -> None:
    engine = _engine_with_defaults()
    event = make_workspace_active_window_changed_event(workspace_id=999, active_window_id=100)
    with pytest.raises(DesyncError):
        reduce_workspace_active_window_changed(engine, event)


def test_reduce_workspace_urgency_changed_sets_urgent() -> None:
    engine = _engine_with_defaults()
    event = make_workspace_urgency_changed_event(id=1, urgent=True)
    domains = reduce_workspace_urgency_changed(engine, event)

    assert engine.workspaces[1].is_urgent is True
    assert ChangedDomain.WORKSPACES in domains


def test_reduce_workspace_urgency_changed_raises_on_unknown() -> None:
    engine = _engine_with_defaults()
    event = make_workspace_urgency_changed_event(id=999, urgent=True)
    with pytest.raises(DesyncError):
        reduce_workspace_urgency_changed(engine, event)


def test_reduce_keyboard_layouts_changed_replaces_layouts() -> None:
    engine = _engine_with_defaults()
    new_layouts = make_keyboard_layouts(names=["FR", "ES"], current_idx=1)
    event = make_keyboard_layouts_changed_event(keyboard_layouts=new_layouts)
    domains = reduce_keyboard_layouts_changed(engine, event)

    assert engine.keyboard_layouts is not None
    assert engine.keyboard_layouts.names == ["FR", "ES"]
    assert domains == frozenset({ChangedDomain.KEYBOARD})


def test_reduce_keyboard_layout_switched_updates_index() -> None:
    engine = _engine_with_defaults()
    event = make_keyboard_layout_switched_event(idx=1)
    domains = reduce_keyboard_layout_switched(engine, event)

    assert engine.keyboard_layouts is not None
    assert engine.keyboard_layouts.current_idx == 1
    assert domains == frozenset({ChangedDomain.KEYBOARD})


def test_reduce_keyboard_layout_switched_raises_when_uninitialized() -> None:
    engine = EngineState.empty()
    engine.overview = make_overview()
    event = make_keyboard_layout_switched_event(idx=0)
    with pytest.raises(DesyncError):
        reduce_keyboard_layout_switched(engine, event)


def test_reduce_overview_opened_or_closed_updates_state() -> None:
    engine = _engine_with_defaults()
    event = make_overview_opened_or_closed_event(is_open=True)
    domains = reduce_overview_opened_or_closed(engine, event)

    assert engine.overview is not None
    assert engine.overview.is_open is True
    assert domains == frozenset({ChangedDomain.OVERVIEW})


def test_reduce_overview_raises_when_uninitialized() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    event = make_overview_opened_or_closed_event(is_open=True)
    with pytest.raises(DesyncError):
        reduce_overview_opened_or_closed(engine, event)


def test_reduce_config_loaded_is_noop() -> None:
    engine = _engine_with_defaults()
    event = make_config_loaded_event()
    domains = reduce_config_loaded(engine, event)
    assert domains == frozenset()


def test_reduce_event_handles_unknown_with_stale_policy() -> None:
    engine = _engine_with_defaults()
    engine.health = HealthState.LIVE
    event = UnknownEvent(variant_name="FutureEvent", raw_payload={})
    config = NiriStateConfig(unknown_event_policy=UnknownEventPolicy.STALE)

    result = reduce_event(engine, event, config=config, revision=1)

    assert result.marked_desync is True
    assert engine.diagnostics.desynced is True


def test_reduce_event_ignores_unknown_with_ignore_policy() -> None:
    engine = _engine_with_defaults()
    event = UnknownEvent(variant_name="FutureEvent", raw_payload={})
    config = NiriStateConfig(unknown_event_policy=UnknownEventPolicy.IGNORE)

    result = reduce_event(engine, event, config=config, revision=1)

    assert result.applied is False
