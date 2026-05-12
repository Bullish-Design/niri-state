from __future__ import annotations

import pytest
from niri_pypc.types.generated.models import KeyboardLayouts

from niri_state._core.models.entities import KeyboardState, OverviewState
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import CompatibilityInfo, DiagnosticsInfo, NiriSnapshot
from niri_state._runtime.store import NiriState
from niri_state.config import NiriStateConfig


def _make_minimal_snapshot(**overrides):
    defaults: dict[str, object] = dict(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_output_name=None,
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard=KeyboardState(
            protocol=KeyboardLayouts(current_idx=0, names=["us"]),
            current_name="us",
        ),
        overview=OverviewState(is_open=False),
        workspaces_by_output={},
        windows_by_workspace={},
        active_workspace_by_output={},
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(),
    )
    defaults.update(overrides)
    return NiriSnapshot(**defaults)


class TestNiriStateStore:
    async def test_revision_monotonicity(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot(revision=5)
        state = NiriState(config)
        state._current_snapshot = snap
        state._revision = 5

        assert state.health == HealthState.LIVE

    async def test_subscribe_returns_iterator(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot()
        state = NiriState(config)
        state._current_snapshot = snap

        sub = state.subscribe()
        assert hasattr(sub, "__aiter__")

    async def test_subscribe_multiple(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot()
        state = NiriState(config)
        state._current_snapshot = snap

        sub1 = state.subscribe()
        sub2 = state.subscribe()

        assert sub1 is not None
        assert sub2 is not None

    async def test_idempotent_close(self) -> None:
        config = NiriStateConfig()
        state = NiriState(config)
        snap = _make_minimal_snapshot()
        state._current_snapshot = snap

        await state.close()
        await state.close()

    async def test_close_cancels_subscribers(self) -> None:
        config = NiriStateConfig()
        snap = _make_minimal_snapshot()
        state = NiriState(config)
        state._current_snapshot = snap

        sub_iter = state.subscribe()
        await state.close()

        with pytest.raises(StopAsyncIteration):
            await sub_iter.__anext__()
