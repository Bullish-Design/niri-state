from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class InvariantViolation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    path: tuple[str | int, ...] = ()
    severity: str = "error"


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
    return diag.model_copy(
        update={
            "event_count": diag.event_count + 1,
            "last_event_type": event_type,
        }
    )


def with_desync(diag: Diagnostics, *, event_type: str, reason: str) -> Diagnostics:
    return diag.model_copy(
        update={
            "desynced": True,
            "last_event_type": event_type,
            "last_error": reason,
        }
    )


def with_invariant_violations(
    diag: Diagnostics,
    *,
    violations: tuple[InvariantViolation, ...],
) -> Diagnostics:
    return diag.model_copy(update={"invariant_violations": violations})


def with_resync(diag: Diagnostics) -> Diagnostics:
    return diag.model_copy(
        update={
            "desynced": False,
            "resync_count": diag.resync_count + 1,
            "last_error": None,
            "invariant_violations": (),
        }
    )


def with_error(diag: Diagnostics, *, message: str) -> Diagnostics:
    return diag.model_copy(update={"last_error": message})


def with_note(diag: Diagnostics, *, note: str) -> Diagnostics:
    return diag.model_copy(update={"notes": diag.notes + (note,)})
