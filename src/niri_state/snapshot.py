from __future__ import annotations

from functools import cached_property
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.protocol import KeyboardLayouts, Output, Overview, Window, Workspace


class Snapshot(BaseModel, frozen=True):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    revision: int
    timestamp: float
    health: HealthState

    outputs: dict[str, Output] | MappingProxyType[str, Output]
    workspaces: dict[int, Workspace] | MappingProxyType[int, Workspace]
    windows: dict[int, Window] | MappingProxyType[int, Window]

    focused_workspace_id: int | None
    focused_window_id: int | None

    keyboard_layouts: KeyboardLayouts
    overview: Overview

    diagnostics: Diagnostics
    compatibility: Compatibility

    @field_validator("outputs", "workspaces", "windows", mode="before")
    @classmethod
    def _freeze_mapping(cls, value: object) -> MappingProxyType[Any, Any]:
        if isinstance(value, MappingProxyType):
            return value
        if isinstance(value, dict):
            return MappingProxyType(dict(value))
        raise TypeError(f"expected dict or MappingProxyType, got {type(value)!r}")

    @cached_property
    def focused_output_name(self) -> str | None:
        if self.focused_workspace_id is None:
            return None
        ws = self.workspaces.get(self.focused_workspace_id)
        if ws is None:
            return None
        return ws.output

    @cached_property
    def workspaces_by_output(self) -> MappingProxyType[str, tuple[int, ...]]:
        buckets: dict[str, list[Workspace]] = {}
        for ws in self.workspaces.values():
            if ws.output is None:
                continue
            buckets.setdefault(ws.output, []).append(ws)
        return MappingProxyType(
            {
                key: tuple(workspace.id for workspace in sorted(value, key=lambda w: (w.idx, w.id)))
                for key, value in buckets.items()
            }
        )

    @cached_property
    def windows_by_workspace(self) -> MappingProxyType[int, tuple[int, ...]]:
        buckets: dict[int, list[int]] = {}
        for window_id, win in self.windows.items():
            if win.workspace_id is None:
                continue
            buckets.setdefault(win.workspace_id, []).append(window_id)
        return MappingProxyType({key: tuple(sorted(value)) for key, value in buckets.items()})

    @cached_property
    def active_workspace_by_output(self) -> MappingProxyType[str, int]:
        active: dict[str, int] = {}
        for workspace_id, ws in self.workspaces.items():
            if ws.is_active:
                active[ws.output] = workspace_id
        return MappingProxyType(active)

    @cached_property
    def keyboard_current_name(self) -> str | None:
        idx = self.keyboard_layouts.current_idx
        names = self.keyboard_layouts.names
        if 0 <= idx < len(names):
            return names[idx]
        return None
