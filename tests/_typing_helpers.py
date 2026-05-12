from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from niri_pypc.types.generated.models import KeyboardLayouts

from niri_state._core.models.entities import KeyboardState, OverviewState
from niri_state._core.models.health import HealthState
from niri_state._core.models.snapshot import CompatibilityInfo, DiagnosticsInfo, NiriSnapshot


def make_minimal_snapshot(**overrides: Any) -> NiriSnapshot:
    snapshot = NiriSnapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs=MappingProxyType({}),
        workspaces=MappingProxyType({}),
        windows=MappingProxyType({}),
        focused_output_name=None,
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard=KeyboardState(protocol=KeyboardLayouts(current_idx=0, names=["us"]), current_name="us"),
        overview=OverviewState(is_open=False),
        workspaces_by_output=MappingProxyType({}),
        windows_by_workspace=MappingProxyType({}),
        active_workspace_by_output=MappingProxyType({}),
        diagnostics=DiagnosticsInfo(),
        compatibility=CompatibilityInfo(),
    )
    if not overrides:
        return snapshot
    return snapshot.model_copy(update=overrides)


def as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}
