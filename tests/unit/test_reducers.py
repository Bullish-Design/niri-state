from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from tests.factories.events import (
    make_window_layouts_changed_event,
    make_window_urgency_changed_event,
    make_workspace_activated_event,
)
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_overview,
    make_window,
    make_workspace,
)

from niri_state.changes import ChangedDomain
from niri_state.engine_state import EngineState
from niri_state.reducers import (
    reduce_window_layouts_changed,
    reduce_window_urgency_changed,
    reduce_windows_changed,
    reduce_workspace_activated,
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
