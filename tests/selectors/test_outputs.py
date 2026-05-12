from __future__ import annotations

from niri_state.selectors import outputs


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


class TestOutputSelectors:
    def test_list_outputs_empty(self) -> None:
        snap = _make_minimal_snapshot()
        result = outputs.list_outputs(snap)
        assert result == []

    def test_list_outputs_returns_list(self) -> None:
        from niri_pypc.types.generated.models import Output

        from niri_state._core.models.entities import OutputState

        snap = _make_minimal_snapshot(
            outputs={
                "DP-1": OutputState(
                    output_name="DP-1",
                    protocol=Output(
                        name="DP-1",
                        make="Dell",
                        model="U2720Q",
                        is_custom_mode=False,
                        modes=[],
                        vrr_supported=False,
                        vrr_enabled=False,
                    ),
                ),
                "DP-2": OutputState(
                    output_name="DP-2",
                    protocol=Output(
                        name="DP-2",
                        make="Dell",
                        model="U2720Q",
                        is_custom_mode=False,
                        modes=[],
                        vrr_supported=False,
                        vrr_enabled=False,
                    ),
                ),
            }
        )
        result = outputs.list_outputs(snap)
        assert len(result) == 2

    def test_get_output_found(self) -> None:
        from niri_pypc.types.generated.models import Output

        from niri_state._core.models.entities import OutputState

        snap = _make_minimal_snapshot(
            outputs={
                "DP-1": OutputState(
                    output_name="DP-1",
                    protocol=Output(
                        name="DP-1",
                        make="Dell",
                        model="U2720Q",
                        is_custom_mode=False,
                        modes=[],
                        vrr_supported=False,
                        vrr_enabled=False,
                    ),
                ),
            }
        )
        result = outputs.get_output(snap, "DP-1")
        assert result is not None
        assert result.output_name == "DP-1"

    def test_get_output_not_found(self) -> None:
        snap = _make_minimal_snapshot()
        result = outputs.get_output(snap, "不存在")
        assert result is None
