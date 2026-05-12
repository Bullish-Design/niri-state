from __future__ import annotations

from types import MappingProxyType

import pytest
from niri_pypc.types.generated.models import KeyboardLayouts
from pydantic import ValidationError

from niri_state._core.models.entities import (
    KeyboardState,
    OverviewState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import (
    CompatibilityInfo,
    DiagnosticsInfo,
    NiriSnapshot,
)


def _make_minimal_snapshot(**overrides: dict[str, object]) -> NiriSnapshot:
    """Build a minimal valid snapshot for testing."""
    defaults: dict[str, object] = {
        "revision": 1,
        "timestamp": 0.0,
        "health": HealthState.LIVE,
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
        "workspaces_by_output": {},
        "windows_by_workspace": {},
        "active_workspace_by_output": {},
        "diagnostics": DiagnosticsInfo(),
        "compatibility": CompatibilityInfo(),
    }
    defaults.update(overrides)
    return NiriSnapshot(**defaults)  # type: ignore[arg-type]


class TestSnapshotImmutability:
    def test_attribute_assignment_raises(self) -> None:
        snap = _make_minimal_snapshot()
        with pytest.raises(ValidationError):
            snap.revision = 2

    def test_entity_map_is_mapping_proxy(self) -> None:
        snap = _make_minimal_snapshot()
        assert isinstance(snap.outputs, MappingProxyType)
        assert isinstance(snap.workspaces, MappingProxyType)
        assert isinstance(snap.windows, MappingProxyType)

    def test_entity_map_mutation_raises(self) -> None:
        snap = _make_minimal_snapshot()
        with pytest.raises(TypeError):
            snap.outputs["test"] = None

    def test_index_map_mutation_raises(self) -> None:
        snap = _make_minimal_snapshot()
        with pytest.raises(TypeError):
            snap.workspaces_by_output["test"] = ()
