from __future__ import annotations

from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, field_validator

from niri_state._core.models.entities import (
    KeyboardState,
    OutputState,
    OverviewState,
    WindowState,
    WorkspaceState,
)
from niri_state._core.models.health import HealthState
from niri_state._core.models.types import (
    OutputName,
    Revision,
    WindowId,
    WorkspaceId,
)


class DiagnosticsInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    last_transition_reason: str | None = None
    unknown_events_seen: int = 0
    last_invariant_violations: tuple[str, ...] | None = None


class CompatibilityInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compositor_version: str | None = None


class NiriSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    revision: Revision
    timestamp: float
    health: HealthState

    outputs: MappingProxyType[OutputName, OutputState]
    workspaces: MappingProxyType[WorkspaceId, WorkspaceState]
    windows: MappingProxyType[WindowId, WindowState]

    focused_output_name: OutputName | None
    focused_workspace_id: WorkspaceId | None
    focused_window_id: WindowId | None

    keyboard: KeyboardState
    overview: OverviewState

    workspaces_by_output: MappingProxyType[OutputName, tuple[WorkspaceId, ...]]
    windows_by_workspace: MappingProxyType[WorkspaceId, tuple[WindowId, ...]]
    active_workspace_by_output: MappingProxyType[OutputName, WorkspaceId]

    diagnostics: DiagnosticsInfo
    compatibility: CompatibilityInfo

    @field_validator(
        "outputs",
        "workspaces",
        "windows",
        "workspaces_by_output",
        "windows_by_workspace",
        "active_workspace_by_output",
        mode="before",
    )
    @classmethod
    def _wrap_in_mapping_proxy(cls, v: dict | MappingProxyType) -> MappingProxyType:
        if isinstance(v, MappingProxyType):
            return v
        return MappingProxyType(v)
