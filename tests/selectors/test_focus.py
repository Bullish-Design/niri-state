from __future__ import annotations

from niri_state.selectors import focus


def _make_minimal_snapshot(**overrides):
    """Build a minimal snapshot for testing."""
    from niri_pypc.types.generated.models import KeyboardLayouts

    from niri_state._core.models.entities import KeyboardState, OverviewState
    from niri_state._core.models.health import HealthState
    from niri_state._core.models.snapshot import (
        CompatibilityInfo,
        DiagnosticsInfo,
        NiriSnapshot,
    )

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
    return NiriSnapshot(**defaults)  # type: ignore[arg-type]


class TestFocusSelectors:
    def test_get_focused_window_id_none(self) -> None:
        snap = _make_minimal_snapshot()
        result = focus.get_focused_window_id(snap)
        assert result is None

    def test_get_focused_workspace_id_none(self) -> None:
        snap = _make_minimal_snapshot()
        result = focus.get_focused_workspace_id(snap)
        assert result is None

    def test_get_focused_output_name_none(self) -> None:
        snap = _make_minimal_snapshot()
        result = focus.get_focused_output_name(snap)
        assert result is None

    def test_get_focused_window_returns_none_when_no_id(self) -> None:
        snap = _make_minimal_snapshot()
        result = focus.get_focused_window(snap)
        assert result is None
