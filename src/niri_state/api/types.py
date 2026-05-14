from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class InvariantViolation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    path: tuple[str | int, ...] = ()
    severity: str = "error"
