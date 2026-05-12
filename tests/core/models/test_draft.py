from __future__ import annotations

from types import MappingProxyType

from niri_pypc.types.generated.models import KeyboardLayouts, Workspace

from niri_state._core.models.draft import DraftState
from niri_state._core.models.entities import (
    KeyboardState,
    OverviewState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import (
    CompatibilityInfo,
    DiagnosticsInfo,
)


def _make_draft(**overrides: dict[str, object]) -> DraftState:
    defaults: dict[str, object] = {
        "outputs": {},
        "workspaces": {},
        "windows": {},
        "focused_output_name": None,
        "focused_workspace_id": None,
        "focused_window_id": None,
        "keyboard": KeyboardState(
            protocol=KeyboardLayouts(current_idx=0, names=["us"]),
            current_name="us",
        ),
        "overview": OverviewState(is_open=False),
        "health": HealthState.LIVE,
        "diagnostics": DiagnosticsInfo(),
        "compatibility": CompatibilityInfo(),
    }
    defaults.update(overrides)
    return DraftState(**defaults)  # type: ignore[arg-type]


class TestDraftState:
    def test_mutable_entity_maps(self) -> None:
        draft = _make_draft()
        ws = Workspace(
            id=1,
            idx=0,
            is_active=True,
            is_focused=True,
            is_urgent=False,
            output="eDP-1",
        )
        draft.workspaces[1] = WorkspaceState(workspace_id=1, protocol=ws)
        assert 1 in draft.workspaces

    def test_freeze_produces_immutable_snapshot(self) -> None:
        draft = _make_draft()
        snap = draft.freeze(revision=1)
        assert snap.revision == 1
        assert isinstance(snap.outputs, MappingProxyType)

    def test_build_indexes_workspaces_by_output(self) -> None:
        ws = Workspace(
            id=1,
            idx=0,
            is_active=True,
            is_focused=False,
            is_urgent=False,
            output="eDP-1",
        )
        draft = _make_draft()
        draft.workspaces[1] = WorkspaceState(workspace_id=1, protocol=ws)
        ws_by_out, _, active_ws = draft.build_indexes()
        assert ws_by_out["eDP-1"] == (1,)
        assert active_ws["eDP-1"] == 1

    def test_from_snapshot_roundtrip(self) -> None:
        draft = _make_draft()
        snap = draft.freeze(revision=1)
        draft2 = DraftState.from_snapshot(snap)
        snap2 = draft2.freeze(revision=2)
        assert snap2.revision == 2
        assert snap2.health == snap.health
