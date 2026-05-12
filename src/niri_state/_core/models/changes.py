from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict

from niri_state._core.models.types import Revision


class ChangeCause(enum.Enum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    RESYNC = "resync"
    STALE_TRANSITION = "stale_transition"
    LIFECYCLE = "lifecycle"


class ChangedDomain(enum.Enum):
    OUTPUTS = "outputs"
    WORKSPACES = "workspaces"
    WINDOWS = "windows"
    FOCUS = "focus"
    KEYBOARD = "keyboard"
    OVERVIEW = "overview"
    HEALTH = "health"


class ChangeSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    revision: Revision
    timestamp: float
    cause: ChangeCause
    changed_domains: frozenset[ChangedDomain]
    event_type: str | None = None
    event_summary: str | None = None
