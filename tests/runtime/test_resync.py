from __future__ import annotations

from niri_pypc.types.generated.models import KeyboardLayouts

from niri_state._core.models.entities import KeyboardState, OverviewState
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import CompatibilityInfo, DiagnosticsInfo, NiriSnapshot
from niri_state._runtime.resync import ResyncCoordinator, create_resync_coordinator
from niri_state._runtime.store import NiriState
from niri_state.config import NiriStateConfig, ResyncPolicy


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


class TestResyncCoordinator:
    async def test_manual_mark_stale_no_auto_resync(self) -> None:
        config = NiriStateConfig(resync_policy=ResyncPolicy.MANUAL)
        state = NiriState(config)
        state._current_snapshot = _make_minimal_snapshot(health=HealthState.LIVE)

        coordinator = ResyncCoordinator(state, config)
        coordinator.mark_stale("test reason")

        assert state.health == HealthState.LIVE

    async def test_auto_mark_stale_triggers_resync(self) -> None:
        config = NiriStateConfig(resync_policy=ResyncPolicy.AUTO)
        state = NiriState(config)
        state._current_snapshot = _make_minimal_snapshot(health=HealthState.LIVE)

        coordinator = ResyncCoordinator(state, config)
        coordinator.mark_stale("test reason")

        assert coordinator._resync_task is not None

    async def test_force_resync_available(self) -> None:
        config = NiriStateConfig(resync_policy=ResyncPolicy.MANUAL)
        state = NiriState(config)
        state._current_snapshot = _make_minimal_snapshot(health=HealthState.LIVE)

        coordinator = ResyncCoordinator(state, config)
        await coordinator.force_resync()

    async def test_create_resync_coordinator_factory(self) -> None:
        config = NiriStateConfig()
        state = NiriState(config)
        state._current_snapshot = _make_minimal_snapshot()

        coordinator = create_resync_coordinator(state, config)
        assert isinstance(coordinator, ResyncCoordinator)
        assert coordinator.policy == config.resync_policy
