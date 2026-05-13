from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ChangeCause(StrEnum):
    BOOTSTRAP = "bootstrap"
    EVENT = "event"
    REFRESH = "refresh"
    RESYNC = "resync"
    CLOSE = "close"
    HEALTH = "health"


class ChangedDomain(StrEnum):
    OUTPUTS = "outputs"
    WORKSPACES = "workspaces"
    WINDOWS = "windows"
    FOCUS = "focus"
    KEYBOARD = "keyboard"
    OVERVIEW = "overview"
    HEALTH = "health"
    DIAGNOSTICS = "diagnostics"


class ChangeSet(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    revision: int
    cause: ChangeCause
    domains: frozenset[ChangedDomain]


def bootstrap_changeset(*, revision: int) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        cause=ChangeCause.BOOTSTRAP,
        domains=frozenset(
            {
                ChangedDomain.OUTPUTS,
                ChangedDomain.WORKSPACES,
                ChangedDomain.WINDOWS,
                ChangedDomain.FOCUS,
                ChangedDomain.KEYBOARD,
                ChangedDomain.OVERVIEW,
                ChangedDomain.HEALTH,
                ChangedDomain.DIAGNOSTICS,
            }
        ),
    )


def event_changeset(
    *,
    revision: int,
    domains: frozenset[ChangedDomain],
) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        cause=ChangeCause.EVENT,
        domains=domains,
    )


def refresh_changeset(
    *,
    revision: int,
    domains: frozenset[ChangedDomain],
) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        cause=ChangeCause.REFRESH,
        domains=domains,
    )


def resync_changeset(
    *,
    revision: int,
    domains: frozenset[ChangedDomain],
) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        cause=ChangeCause.RESYNC,
        domains=domains,
    )


def health_changeset(*, revision: int) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        cause=ChangeCause.HEALTH,
        domains=frozenset({ChangedDomain.HEALTH, ChangedDomain.DIAGNOSTICS}),
    )


def close_changeset(*, revision: int) -> ChangeSet:
    return ChangeSet(
        revision=revision,
        cause=ChangeCause.CLOSE,
        domains=frozenset({ChangedDomain.HEALTH}),
    )
