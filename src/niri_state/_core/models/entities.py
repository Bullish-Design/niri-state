from __future__ import annotations

from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Window,
    Workspace,
)
from pydantic import BaseModel, ConfigDict


class OutputState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    output_name: str
    protocol: Output


class WorkspaceState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workspace_id: int
    protocol: Workspace


class WindowState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    window_id: int
    protocol: Window


class KeyboardState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    protocol: KeyboardLayouts
    current_name: str | None
    """Derived from protocol.names[protocol.current_idx] with bounds check."""


class OverviewState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    is_open: bool
