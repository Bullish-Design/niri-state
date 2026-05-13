from __future__ import annotations

from niri_state.changes import ChangedDomain
from niri_state.engine_state import EngineState
from niri_state.reducers import reduce_windows_changed
from tests.factories.protocol import make_keyboard_layouts, make_overview, make_window


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
