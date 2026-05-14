from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from niri_state.api.types import InvariantViolation


class Compatibility(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    niri_version: str | None = None
    schema_version: str | None = None
    warnings: tuple[str, ...] = ()


class Diagnostics(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    desynced: bool = False
    resync_count: int = 0
    event_count: int = 0
    last_event_type: str | None = None
    last_error: str | None = None
    invariant_violations: tuple[InvariantViolation, ...] = ()
    notes: tuple[str, ...] = ()


def with_event_applied(diag: Diagnostics, *, event_type: str) -> Diagnostics:
    update = cast(Mapping[str, Any], {"event_count": diag.event_count + 1, "last_event_type": event_type})
    return diag.model_copy(update=update)


def with_desync(diag: Diagnostics, *, event_type: str, reason: str) -> Diagnostics:
    update = cast(
        Mapping[str, Any],
        {
            "desynced": True,
            "last_event_type": event_type,
            "last_error": reason,
        },
    )
    return diag.model_copy(update=update)


def with_invariant_violations(
    diag: Diagnostics,
    *,
    violations: tuple[InvariantViolation, ...],
) -> Diagnostics:
    update = cast(Mapping[str, Any], {"invariant_violations": violations})
    return diag.model_copy(update=update)


def with_resync(diag: Diagnostics) -> Diagnostics:
    update = cast(
        Mapping[str, Any],
        {
            "desynced": False,
            "resync_count": diag.resync_count + 1,
            "last_error": None,
            "invariant_violations": (),
        },
    )
    return diag.model_copy(update=update)


def with_error(diag: Diagnostics, *, message: str) -> Diagnostics:
    update = cast(Mapping[str, Any], {"last_error": message})
    return diag.model_copy(update=update)


def with_note(diag: Diagnostics, *, note: str) -> Diagnostics:
    update = cast(Mapping[str, Any], {"notes": diag.notes + (note,)})
    return diag.model_copy(update=update)
