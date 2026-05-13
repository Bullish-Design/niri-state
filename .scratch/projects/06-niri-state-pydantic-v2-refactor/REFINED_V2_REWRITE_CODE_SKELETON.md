Part 1 of 3 — consolidated package tree and core state layer.

I’m folding in the small fixes from the earlier skeleton as I go, so this version is the cleaned-up one.

---

## Package tree

```text id="pk3kx9"
src/niri_state/
  __init__.py
  protocol.py
  config.py
  errors.py
  health.py
  diagnostics.py
  changes.py

  snapshot.py
  engine_state.py
  reconcile.py
  invariants.py

  bootstrap.py
  reducers.py
  broadcaster.py
  resync.py
  store.py
  waiters.py

  selectors/
    __init__.py
    focus.py
    outputs.py
    workspaces.py
    windows.py
    keyboard.py
    overview.py
    aggregates.py

tests/
  factories/
    __init__.py
    protocol.py
    raw_frames.py

  unit/
    test_config.py
    test_health.py
    test_diagnostics.py
    test_snapshot.py
    test_reconcile.py
    test_invariants.py
    test_reducers.py
    test_selectors.py
    test_broadcaster.py
    test_resync.py
    test_waiters.py

  integration/
    test_bootstrap.py
    test_runtime_mutation_loop.py
    test_refresh.py
    test_desync_and_auto_resync.py
    test_close_lifecycle.py

  replay/
    test_replay_traces.py
```

---

## `src/niri_state/__init__.py`

```python id="trghrr"
from niri_state.changes import ChangeCause, ChangeSet, ChangedDomain
from niri_state.config import (
    InvariantFailurePolicy,
    NiriStateConfig,
    ResyncPolicy,
    SubscriberOverflowPolicy,
    UnknownEventPolicy,
    WaitHealthPolicy,
    strict_config,
)
from niri_state.errors import (
    BootstrapError,
    DesyncError,
    InvariantError,
    NiriStateError,
    ReductionError,
    ResyncError,
    StateConfigError,
    StateLifecycleError,
    SubscriptionOverflowError,
    WaitTimeoutError,
)
from niri_state.health import HealthState
from niri_state.snapshot import Snapshot
from niri_state.store import NiriState

__all__ = [
    "BootstrapError",
    "ChangeCause",
    "ChangeSet",
    "ChangedDomain",
    "DesyncError",
    "HealthState",
    "InvariantError",
    "InvariantFailurePolicy",
    "NiriState",
    "NiriStateConfig",
    "NiriStateError",
    "ReductionError",
    "ResyncError",
    "ResyncPolicy",
    "Snapshot",
    "StateConfigError",
    "StateLifecycleError",
    "SubscriberOverflowPolicy",
    "SubscriptionOverflowError",
    "UnknownEventPolicy",
    "WaitHealthPolicy",
    "WaitTimeoutError",
    "strict_config",
]
```

---

## `src/niri_state/protocol.py`

```python id="jlwmqy"
from __future__ import annotations

from niri_pypc import NiriClient, NiriConnectionBundle
from niri_pypc.types.generated.event import (
    ConfigLoadedEvent,
    EventValue,
    KeyboardLayoutsChangedEvent,
    KeyboardLayoutSwitchedEvent,
    OverviewOpenedOrClosedEvent,
    ScreenshotCapturedEvent,
    UnknownEvent,
    WindowClosedEvent,
    WindowFocusChangedEvent,
    WindowFocusTimestampChangedEvent,
    WindowLayoutsChangedEvent,
    WindowOpenedOrChangedEvent,
    WindowsChangedEvent,
    WindowUrgencyChangedEvent,
    WorkspaceActivatedEvent,
    WorkspaceActiveWindowChangedEvent,
    WorkspacesChangedEvent,
    WorkspaceUrgencyChangedEvent,
)
from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    Workspace,
)
from niri_pypc.types.generated.reply import (
    FocusedOutputResponse,
    FocusedWindowResponse,
    KeyboardLayoutsResponse,
    OutputsResponse,
    OverviewStateResponse,
    VersionResponse,
    WindowsResponse,
    WorkspacesResponse,
)
from niri_pypc.types.generated.request import (
    FocusedOutputRequest,
    FocusedWindowRequest,
    KeyboardLayoutsRequest,
    OutputsRequest,
    OverviewStateRequest,
    VersionRequest,
    WindowsRequest,
    WorkspacesRequest,
)

__all__ = [
    "ConfigLoadedEvent",
    "EventValue",
    "FocusedOutputRequest",
    "FocusedOutputResponse",
    "FocusedWindowRequest",
    "FocusedWindowResponse",
    "KeyboardLayouts",
    "KeyboardLayoutsChangedEvent",
    "KeyboardLayoutSwitchedEvent",
    "KeyboardLayoutsRequest",
    "KeyboardLayoutsResponse",
    "NiriClient",
    "NiriConnectionBundle",
    "Output",
    "OutputsRequest",
    "OutputsResponse",
    "Overview",
    "OverviewOpenedOrClosedEvent",
    "OverviewStateRequest",
    "OverviewStateResponse",
    "ScreenshotCapturedEvent",
    "UnknownEvent",
    "VersionRequest",
    "VersionResponse",
    "Window",
    "WindowClosedEvent",
    "WindowFocusChangedEvent",
    "WindowFocusTimestampChangedEvent",
    "WindowLayoutsChangedEvent",
    "WindowOpenedOrChangedEvent",
    "WindowsChangedEvent",
    "WindowsRequest",
    "WindowsResponse",
    "WindowUrgencyChangedEvent",
    "Workspace",
    "WorkspaceActivatedEvent",
    "WorkspaceActiveWindowChangedEvent",
    "WorkspacesChangedEvent",
    "WorkspacesRequest",
    "WorkspacesResponse",
    "WorkspaceUrgencyChangedEvent",
]
```

---

## `src/niri_state/config.py`

```python id="tplwm1"
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt

from niri_pypc import BackpressureMode, NiriConfig


class UnknownEventPolicy(StrEnum):
    STALE = "stale"
    FAIL = "fail"
    IGNORE = "ignore"


class InvariantFailurePolicy(StrEnum):
    STALE = "stale"
    FAIL = "fail"


class ResyncPolicy(StrEnum):
    MANUAL = "manual"
    AUTO = "auto"


class WaitHealthPolicy(StrEnum):
    LIVE_ONLY = "live_only"
    ALLOW_STALE = "allow_stale"


class SubscriberOverflowPolicy(StrEnum):
    DROP_OLDEST = "drop_oldest"
    FAIL_FAST = "fail_fast"


class NiriStateConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    pypc: NiriConfig = Field(default_factory=NiriConfig)

    unknown_event_policy: UnknownEventPolicy = UnknownEventPolicy.STALE
    invariant_failure_policy: InvariantFailurePolicy = InvariantFailurePolicy.STALE
    resync_policy: ResyncPolicy = ResyncPolicy.MANUAL
    wait_health_policy: WaitHealthPolicy = WaitHealthPolicy.LIVE_ONLY
    subscriber_overflow_policy: SubscriberOverflowPolicy = (
        SubscriberOverflowPolicy.DROP_OLDEST
    )

    subscriber_queue_size: PositiveInt = 64
    resync_max_attempts: PositiveInt = 3
    resync_backoff_base: PositiveFloat = 1.0


def strict_config(**overrides: object) -> NiriStateConfig:
    base = NiriStateConfig(**overrides)
    return base.model_copy(
        update={
            "pypc": base.pypc.model_copy(
                update={"backpressure_mode": BackpressureMode.FAIL_FAST}
            ),
            "unknown_event_policy": UnknownEventPolicy.FAIL,
            "invariant_failure_policy": InvariantFailurePolicy.FAIL,
            "subscriber_overflow_policy": SubscriberOverflowPolicy.FAIL_FAST,
        }
    )
```

---

## `src/niri_state/errors.py`

```python id="h9ohw7"
from __future__ import annotations

from typing import TYPE_CHECKING

from niri_state.diagnostics import InvariantViolation

if TYPE_CHECKING:
    from niri_state.health import HealthState


class NiriStateError(Exception):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.operation = operation
        self.retryable = retryable
        self.cause = cause
        super().__init__(message)


class StateConfigError(NiriStateError):
    pass


class StateLifecycleError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        current_state: HealthState | None = None,
        target_state: HealthState | None = None,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )


class BootstrapError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        query: str | None = None,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.query = query
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )


class ReductionError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        event_type: str | None = None,
        revision: int | None = None,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.event_type = event_type
        self.revision = revision
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )


class InvariantError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        violations: tuple[InvariantViolation, ...],
        revision: int,
        operation: str | None = None,
    ) -> None:
        self.violations = violations
        self.revision = revision
        super().__init__(message, operation=operation, retryable=False)


class DesyncError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        event_type: str | None = None,
        revision: int | None = None,
        operation: str | None = None,
        retryable: bool = True,
        cause: Exception | None = None,
    ) -> None:
        self.event_type = event_type
        self.revision = revision
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )


class ResyncError(NiriStateError):
    pass


class SubscriptionOverflowError(NiriStateError):
    pass


class WaitTimeoutError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        timeout: float,
        operation: str | None = None,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        self.timeout = timeout
        super().__init__(
            message,
            operation=operation,
            retryable=retryable,
            cause=cause,
        )
```

---

## `src/niri_state/health.py`

```python id="dwo04v"
from __future__ import annotations

from enum import StrEnum

from niri_state.errors import StateLifecycleError


class HealthState(StrEnum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"


_ALLOWED_TRANSITIONS: dict[HealthState, frozenset[HealthState]] = {
    HealthState.BOOTSTRAPPING: frozenset(
        {
            HealthState.LIVE,
            HealthState.STALE,
            HealthState.CLOSED,
            HealthState.FAILED,
        }
    ),
    HealthState.LIVE: frozenset(
        {
            HealthState.STALE,
            HealthState.RESYNCING,
            HealthState.CLOSED,
            HealthState.FAILED,
        }
    ),
    HealthState.STALE: frozenset(
        {
            HealthState.RESYNCING,
            HealthState.LIVE,
            HealthState.CLOSED,
            HealthState.FAILED,
        }
    ),
    HealthState.RESYNCING: frozenset(
        {
            HealthState.LIVE,
            HealthState.STALE,
            HealthState.CLOSED,
            HealthState.FAILED,
        }
    ),
    HealthState.CLOSED: frozenset(),
    HealthState.FAILED: frozenset(),
}


def validate_transition(current: HealthState, target: HealthState) -> None:
    if current == target:
        return

    allowed = _ALLOWED_TRANSITIONS[current]
    if target not in allowed:
        raise StateLifecycleError(
            f"invalid health transition: {current!s} -> {target!s}",
            current_state=current,
            target_state=target,
            operation="health_transition",
        )
```

---

## `src/niri_state/diagnostics.py`

```python id="jlwmf6"
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
```

---

## `src/niri_state/changes.py`

```python id="0vuw6e"
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
```

---

## `src/niri_state/snapshot.py`

```python id="4jqxzr"
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

    outputs: MappingProxyType[str, Output]
    workspaces: MappingProxyType[int, Workspace]
    windows: MappingProxyType[int, Window]

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
        buckets: dict[str, list[int]] = {}
        for workspace_id, ws in self.workspaces.items():
            buckets.setdefault(ws.output, []).append(workspace_id)
        return MappingProxyType({key: tuple(value) for key, value in buckets.items()})

    @cached_property
    def windows_by_workspace(self) -> MappingProxyType[int, tuple[int, ...]]:
        buckets: dict[int, list[int]] = {}
        for window_id, win in self.windows.items():
            if win.workspace_id is None:
                continue
            buckets.setdefault(win.workspace_id, []).append(window_id)
        return MappingProxyType({key: tuple(value) for key, value in buckets.items()})

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
```

---

## `src/niri_state/engine_state.py`

```python id="v7up1m"
from __future__ import annotations

from dataclasses import dataclass, field
from time import time

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.protocol import KeyboardLayouts, Output, Overview, Window, Workspace
from niri_state.snapshot import Snapshot


@dataclass(slots=True)
class EngineState:
    outputs: dict[str, Output] = field(default_factory=dict)
    workspaces: dict[int, Workspace] = field(default_factory=dict)
    windows: dict[int, Window] = field(default_factory=dict)

    focused_workspace_id: int | None = None
    focused_window_id: int | None = None

    keyboard_layouts: KeyboardLayouts | None = None
    overview: Overview | None = None

    health: HealthState = HealthState.BOOTSTRAPPING
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    compatibility: Compatibility = field(default_factory=Compatibility)

    @classmethod
    def empty(cls) -> EngineState:
        return cls()

    def require_initialized(self) -> None:
        if self.keyboard_layouts is None:
            raise RuntimeError("engine_state.keyboard_layouts is not initialized")
        if self.overview is None:
            raise RuntimeError("engine_state.overview is not initialized")

    def freeze(self, *, revision: int, timestamp: float | None = None) -> Snapshot:
        self.require_initialized()
        return Snapshot(
            revision=revision,
            timestamp=time() if timestamp is None else timestamp,
            health=self.health,
            outputs=self.outputs,
            workspaces=self.workspaces,
            windows=self.windows,
            focused_workspace_id=self.focused_workspace_id,
            focused_window_id=self.focused_window_id,
            keyboard_layouts=self.keyboard_layouts,
            overview=self.overview,
            diagnostics=self.diagnostics,
            compatibility=self.compatibility,
        )
```

---

## `src/niri_state/reconcile.py`

```python id="rri8y4"
from __future__ import annotations

from niri_state.engine_state import EngineState


def reconcile(engine: EngineState) -> None:
    _reconcile_focused_window(engine)
    _reconcile_focused_workspace(engine)
    _reconcile_keyboard(engine)
    _reconcile_workspace_window_relationships(engine)
    _reconcile_diagnostics(engine)


def _reconcile_focused_window(engine: EngineState) -> None:
    if engine.focused_window_id is None:
        return

    win = engine.windows.get(engine.focused_window_id)
    if win is None:
        engine.focused_window_id = None
        return

    if win.workspace_id is not None:
        engine.focused_workspace_id = win.workspace_id


def _reconcile_focused_workspace(engine: EngineState) -> None:
    if (
        engine.focused_workspace_id is not None
        and engine.focused_workspace_id not in engine.workspaces
    ):
        engine.focused_workspace_id = None

    if engine.focused_workspace_id is not None:
        return

    for workspace_id, ws in engine.workspaces.items():
        if ws.is_focused:
            engine.focused_workspace_id = workspace_id
            return


def _reconcile_keyboard(engine: EngineState) -> None:
    return


def _reconcile_workspace_window_relationships(engine: EngineState) -> None:
    return


def _reconcile_diagnostics(engine: EngineState) -> None:
    return
```

---

## `src/niri_state/invariants.py`

```python id="7y61xm"
from __future__ import annotations

from niri_state.diagnostics import InvariantViolation
from niri_state.errors import InvariantError
from niri_state.snapshot import Snapshot


def collect_invariant_violations(snapshot: Snapshot) -> tuple[InvariantViolation, ...]:
    violations: list[InvariantViolation] = []

    if (
        snapshot.focused_window_id is not None
        and snapshot.focused_window_id not in snapshot.windows
    ):
        violations.append(
            InvariantViolation(
                code="focused_window_missing",
                message="focused_window_id does not reference an existing window",
                path=("focused_window_id",),
            )
        )

    if (
        snapshot.focused_workspace_id is not None
        and snapshot.focused_workspace_id not in snapshot.workspaces
    ):
        violations.append(
            InvariantViolation(
                code="focused_workspace_missing",
                message="focused_workspace_id does not reference an existing workspace",
                path=("focused_workspace_id",),
            )
        )

    for window_id, win in snapshot.windows.items():
        if win.workspace_id is None:
            continue
        if win.workspace_id not in snapshot.workspaces:
            violations.append(
                InvariantViolation(
                    code="window_workspace_missing",
                    message="window references missing workspace",
                    path=("windows", window_id, "workspace_id"),
                )
            )

    for workspace_id, ws in snapshot.workspaces.items():
        if ws.output not in snapshot.outputs:
            violations.append(
                InvariantViolation(
                    code="workspace_output_missing",
                    message="workspace references missing output",
                    path=("workspaces", workspace_id, "output"),
                )
            )

    for output_name, workspace_id in snapshot.active_workspace_by_output.items():
        ws = snapshot.workspaces.get(workspace_id)
        if ws is None or ws.output != output_name or not ws.is_active:
            violations.append(
                InvariantViolation(
                    code="active_workspace_mismatch",
                    message="active_workspace_by_output is inconsistent with workspace state",
                    path=("active_workspace_by_output", output_name),
                )
            )

    return tuple(violations)


def assert_invariants(snapshot: Snapshot) -> None:
    violations = collect_invariant_violations(snapshot)
    if not violations:
        return

    raise InvariantError(
        "snapshot invariants violated",
        violations=violations,
        revision=snapshot.revision,
        operation="assert_invariants",
    )
```

---

That is the consolidated core.

---

Part 2 of 3 — consolidated runtime and reduction layer.

This folds the earlier skeleton into one clean runtime pass.

---

## `src/niri_state/bootstrap.py`

```python id="smfuiy"
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from niri_state.changes import ChangeSet, bootstrap_changeset
from niri_state.config import InvariantFailurePolicy, NiriStateConfig
from niri_state.diagnostics import Compatibility, Diagnostics, with_invariant_violations, with_note
from niri_state.engine_state import EngineState
from niri_state.errors import BootstrapError, InvariantError
from niri_state.health import HealthState
from niri_state.invariants import collect_invariant_violations
from niri_state.protocol import (
    FocusedOutputRequest,
    FocusedWindowRequest,
    KeyboardLayouts,
    KeyboardLayoutsRequest,
    NiriClient,
    NiriConnectionBundle,
    Output,
    OutputsRequest,
    Overview,
    OverviewStateRequest,
    VersionRequest,
    Window,
    WindowsRequest,
    Workspace,
    WorkspacesRequest,
)
from niri_state.reconcile import reconcile
from niri_state.snapshot import Snapshot


class BootstrapOutcome(BaseModel, frozen=True):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    engine: EngineState
    initial_snapshot: Snapshot
    initial_changeset: ChangeSet


async def query_outputs(client: NiriClient) -> dict[str, Output]:
    response = await client.request(OutputsRequest())
    return response.payload


async def query_workspaces(client: NiriClient) -> list[Workspace]:
    response = await client.request(WorkspacesRequest())
    return response.payload


async def query_windows(client: NiriClient) -> list[Window]:
    response = await client.request(WindowsRequest())
    return response.payload


async def query_focused_output(client: NiriClient) -> Output | None:
    response = await client.request(FocusedOutputRequest())
    return response.payload


async def query_focused_window(client: NiriClient) -> Window | None:
    response = await client.request(FocusedWindowRequest())
    return response.payload


async def query_keyboard_layouts(client: NiriClient) -> KeyboardLayouts:
    response = await client.request(KeyboardLayoutsRequest())
    return response.payload


async def query_overview(client: NiriClient) -> Overview:
    response = await client.request(OverviewStateRequest())
    return response.payload


async def query_version(client: NiriClient) -> str | None:
    response = await client.request(VersionRequest())
    payload = response.payload

    if payload is None:
        return None
    if isinstance(payload, str):
        return payload
    if hasattr(payload, "version"):
        return payload.version
    return str(payload)


async def build_initial_engine_state(client: NiriClient) -> EngineState:
    outputs = await query_outputs(client)
    workspaces = await query_workspaces(client)
    windows = await query_windows(client)
    focused_output = await query_focused_output(client)
    focused_window = await query_focused_window(client)
    keyboard_layouts = await query_keyboard_layouts(client)
    overview = await query_overview(client)
    version = await query_version(client)

    engine = EngineState.empty()
    engine.outputs = dict(outputs)
    engine.workspaces = {workspace.id: workspace for workspace in workspaces}
    engine.windows = {window.id: window for window in windows}
    engine.keyboard_layouts = keyboard_layouts
    engine.overview = overview
    engine.health = HealthState.BOOTSTRAPPING
    engine.diagnostics = Diagnostics()
    engine.compatibility = Compatibility(niri_version=version)

    if focused_window is not None:
        engine.focused_window_id = focused_window.id
        engine.focused_workspace_id = focused_window.workspace_id

    if focused_output is not None and engine.focused_workspace_id is not None:
        workspace = engine.workspaces.get(engine.focused_workspace_id)
        if workspace is not None and workspace.output != focused_output.name:
            engine.diagnostics = with_note(
                engine.diagnostics,
                note="focused_output query disagreed with focused workspace output",
            )

    reconcile(engine)
    return engine


def _apply_bootstrap_invariant_policy(
    engine: EngineState,
    *,
    snapshot: Snapshot,
    config: NiriStateConfig,
) -> Snapshot:
    violations = collect_invariant_violations(snapshot)
    if not violations:
        return snapshot

    if config.invariant_failure_policy is InvariantFailurePolicy.FAIL:
        raise InvariantError(
            "bootstrap snapshot invariants violated",
            violations=violations,
            revision=snapshot.revision,
            operation="bootstrap",
        )

    engine.diagnostics = with_invariant_violations(
        engine.diagnostics,
        violations=violations,
    )
    engine.health = HealthState.STALE
    reconcile(engine)
    return engine.freeze(revision=snapshot.revision, timestamp=snapshot.timestamp)


async def run_bootstrap(
    bundle: NiriConnectionBundle,
    *,
    config: NiriStateConfig,
) -> BootstrapOutcome:
    try:
        engine = await build_initial_engine_state(bundle.client)
        engine.health = HealthState.LIVE

        snapshot = engine.freeze(revision=1)
        snapshot = _apply_bootstrap_invariant_policy(
            engine,
            snapshot=snapshot,
            config=config,
        )

        return BootstrapOutcome(
            engine=engine,
            initial_snapshot=snapshot,
            initial_changeset=bootstrap_changeset(revision=snapshot.revision),
        )
    except InvariantError:
        raise
    except Exception as exc:
        raise BootstrapError(
            "failed to bootstrap initial niri state",
            operation="bootstrap",
            retryable=True,
            cause=exc,
        ) from exc
```

---

## `src/niri_state/reducers.py`

```python id="e3xz9z"
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from niri_state.changes import ChangedDomain
from niri_state.config import NiriStateConfig, UnknownEventPolicy
from niri_state.diagnostics import with_desync, with_event_applied
from niri_state.engine_state import EngineState
from niri_state.errors import DesyncError, ReductionError
from niri_state.protocol import (
    ConfigLoadedEvent,
    EventValue,
    KeyboardLayoutsChangedEvent,
    KeyboardLayoutSwitchedEvent,
    OverviewOpenedOrClosedEvent,
    ScreenshotCapturedEvent,
    WindowClosedEvent,
    WindowFocusChangedEvent,
    WindowFocusTimestampChangedEvent,
    WindowLayoutsChangedEvent,
    WindowOpenedOrChangedEvent,
    WindowsChangedEvent,
    WindowUrgencyChangedEvent,
    WorkspaceActivatedEvent,
    WorkspaceActiveWindowChangedEvent,
    WorkspacesChangedEvent,
    WorkspaceUrgencyChangedEvent,
)


@dataclass(frozen=True, slots=True)
class ReduceResult:
    applied: bool
    domains: frozenset[ChangedDomain]
    marked_desync: bool = False


Reducer = Callable[[EngineState, object], frozenset[ChangedDomain]]
EVENT_REDUCERS: dict[type[EventValue], Reducer] = {}


def register(event_type: type[EventValue]) -> Callable[[Reducer], Reducer]:
    def decorator(fn: Reducer) -> Reducer:
        EVENT_REDUCERS[event_type] = fn
        return fn

    return decorator


def reduce_event(
    engine: EngineState,
    event: EventValue,
    *,
    config: NiriStateConfig,
    revision: int,
) -> ReduceResult:
    event_type = type(event).__name__
    engine.diagnostics = with_event_applied(engine.diagnostics, event_type=event_type)

    reducer = EVENT_REDUCERS.get(type(event))
    if reducer is None:
        return _handle_unknown_event(
            engine,
            event,
            config=config,
            revision=revision,
        )

    try:
        domains = reducer(engine, event)
        return ReduceResult(applied=True, domains=domains)
    except DesyncError:
        raise
    except Exception as exc:
        raise ReductionError(
            f"failed reducing event {event_type}",
            event_type=event_type,
            revision=revision,
            operation="reduce_event",
            cause=exc,
        ) from exc


@register(WindowsChangedEvent)
def reduce_windows_changed(
    engine: EngineState,
    event: WindowsChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.windows = {window.id: window for window in event.windows}
    return frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})


@register(WindowOpenedOrChangedEvent)
def reduce_window_opened_or_changed(
    engine: EngineState,
    event: WindowOpenedOrChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.windows[event.window.id] = event.window

    domains = {ChangedDomain.WINDOWS}
    if event.window.is_focused:
        engine.focused_window_id = event.window.id
        domains.add(ChangedDomain.FOCUS)

    return frozenset(domains)


@register(WindowClosedEvent)
def reduce_window_closed(
    engine: EngineState,
    event: WindowClosedEvent,
) -> frozenset[ChangedDomain]:
    engine.windows.pop(event.id, None)

    if engine.focused_window_id == event.id:
        engine.focused_window_id = None
        return frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})

    return frozenset({ChangedDomain.WINDOWS})


@register(WindowFocusChangedEvent)
def reduce_window_focus_changed(
    engine: EngineState,
    event: WindowFocusChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.focused_window_id = event.id
    return frozenset({ChangedDomain.FOCUS})


@register(WindowUrgencyChangedEvent)
def reduce_window_urgency_changed(
    engine: EngineState,
    event: WindowUrgencyChangedEvent,
) -> frozenset[ChangedDomain]:
    window = engine.windows.get(event.id)
    if window is None:
        raise DesyncError(
            "window urgency changed for unknown window",
            event_type=type(event).__name__,
            operation="reduce_window_urgency_changed",
        )

    engine.windows[event.id] = window.model_copy(update={"is_urgent": event.is_urgent})
    return frozenset({ChangedDomain.WINDOWS})


@register(WindowFocusTimestampChangedEvent)
def reduce_window_focus_timestamp_changed(
    engine: EngineState,
    event: WindowFocusTimestampChangedEvent,
) -> frozenset[ChangedDomain]:
    window = engine.windows.get(event.id)
    if window is None:
        raise DesyncError(
            "window focus timestamp changed for unknown window",
            event_type=type(event).__name__,
            operation="reduce_window_focus_timestamp_changed",
        )

    engine.windows[event.id] = window.model_copy(
        update={"focus_timestamp": event.focus_timestamp}
    )
    return frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})


@register(WindowLayoutsChangedEvent)
def reduce_window_layouts_changed(
    engine: EngineState,
    event: WindowLayoutsChangedEvent,
) -> frozenset[ChangedDomain]:
    window = engine.windows.get(event.id)
    if window is None:
        raise DesyncError(
            "window layout changed for unknown window",
            event_type=type(event).__name__,
            operation="reduce_window_layouts_changed",
        )

    engine.windows[event.id] = window.model_copy(update={"layout": event.layout})
    return frozenset({ChangedDomain.WINDOWS})


@register(WorkspacesChangedEvent)
def reduce_workspaces_changed(
    engine: EngineState,
    event: WorkspacesChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.workspaces = {workspace.id: workspace for workspace in event.workspaces}
    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})


@register(WorkspaceActivatedEvent)
def reduce_workspace_activated(
    engine: EngineState,
    event: WorkspaceActivatedEvent,
) -> frozenset[ChangedDomain]:
    workspace = engine.workspaces.get(event.id)
    if workspace is None:
        raise DesyncError(
            "workspace activated for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_activated",
        )

    updated: dict[int, object] = {}
    for workspace_id, existing in engine.workspaces.items():
        if existing.output != workspace.output:
            continue
        if existing.is_active or existing.is_focused:
            updated[workspace_id] = existing.model_copy(
                update={"is_active": False, "is_focused": False}
            )

    engine.workspaces.update(updated)
    engine.workspaces[event.id] = workspace.model_copy(
        update={"is_active": True, "is_focused": True}
    )
    engine.focused_workspace_id = event.id

    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})


@register(WorkspaceActiveWindowChangedEvent)
def reduce_workspace_active_window_changed(
    engine: EngineState,
    event: WorkspaceActiveWindowChangedEvent,
) -> frozenset[ChangedDomain]:
    workspace = engine.workspaces.get(event.workspace_id)
    if workspace is None:
        raise DesyncError(
            "workspace active window changed for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_active_window_changed",
        )

    engine.workspaces[event.workspace_id] = workspace.model_copy(
        update={"active_window_id": event.active_window_id}
    )
    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})


@register(WorkspaceUrgencyChangedEvent)
def reduce_workspace_urgency_changed(
    engine: EngineState,
    event: WorkspaceUrgencyChangedEvent,
) -> frozenset[ChangedDomain]:
    workspace = engine.workspaces.get(event.id)
    if workspace is None:
        raise DesyncError(
            "workspace urgency changed for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_urgency_changed",
        )

    engine.workspaces[event.id] = workspace.model_copy(
        update={"is_urgent": event.is_urgent}
    )
    return frozenset({ChangedDomain.WORKSPACES})


@register(KeyboardLayoutsChangedEvent)
def reduce_keyboard_layouts_changed(
    engine: EngineState,
    event: KeyboardLayoutsChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.keyboard_layouts = event.keyboard_layouts
    return frozenset({ChangedDomain.KEYBOARD})


@register(KeyboardLayoutSwitchedEvent)
def reduce_keyboard_layout_switched(
    engine: EngineState,
    event: KeyboardLayoutSwitchedEvent,
) -> frozenset[ChangedDomain]:
    current = engine.keyboard_layouts
    if current is None:
        raise DesyncError(
            "keyboard layout switched before keyboard state initialized",
            event_type=type(event).__name__,
            operation="reduce_keyboard_layout_switched",
        )

    engine.keyboard_layouts = current.model_copy(update={"current_idx": event.idx})
    return frozenset({ChangedDomain.KEYBOARD})


@register(OverviewOpenedOrClosedEvent)
def reduce_overview_opened_or_closed(
    engine: EngineState,
    event: OverviewOpenedOrClosedEvent,
) -> frozenset[ChangedDomain]:
    current = engine.overview
    if current is None:
        raise DesyncError(
            "overview changed before overview state initialized",
            event_type=type(event).__name__,
            operation="reduce_overview_opened_or_closed",
        )

    engine.overview = current.model_copy(update={"is_open": event.is_open})
    return frozenset({ChangedDomain.OVERVIEW})


@register(ConfigLoadedEvent)
def reduce_config_loaded(
    engine: EngineState,
    event: ConfigLoadedEvent,
) -> frozenset[ChangedDomain]:
    return frozenset()


@register(ScreenshotCapturedEvent)
def reduce_screenshot_captured(
    engine: EngineState,
    event: ScreenshotCapturedEvent,
) -> frozenset[ChangedDomain]:
    return frozenset()


def _handle_unknown_event(
    engine: EngineState,
    event: EventValue,
    *,
    config: NiriStateConfig,
    revision: int,
) -> ReduceResult:
    event_type = type(event).__name__
    policy = config.unknown_event_policy

    if policy is UnknownEventPolicy.IGNORE:
        return ReduceResult(applied=False, domains=frozenset())

    if policy is UnknownEventPolicy.STALE:
        engine.diagnostics = with_desync(
            engine.diagnostics,
            event_type=event_type,
            reason="unknown event",
        )
        return ReduceResult(
            applied=True,
            domains=frozenset({ChangedDomain.DIAGNOSTICS}),
            marked_desync=True,
        )

    raise DesyncError(
        "unknown event encountered",
        event_type=event_type,
        revision=revision,
        operation="unknown_event",
    )
```

---

## `src/niri_state/broadcaster.py`

```python id="98rk8b"
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

from niri_state.changes import ChangeSet
from niri_state.config import NiriStateConfig, SubscriberOverflowPolicy
from niri_state.errors import SubscriptionOverflowError
from niri_state.snapshot import Snapshot


@dataclass(frozen=True, slots=True)
class PublishedState:
    snapshot: Snapshot
    changes: ChangeSet


@dataclass(eq=False, slots=True)
class _Subscriber:
    queue: asyncio.Queue[PublishedState | None]


class Broadcaster:
    def __init__(self, config: NiriStateConfig) -> None:
        self._config = config
        self._subscribers: set[_Subscriber] = set()
        self._closed = False

    def subscribe(self) -> AsyncIterator[PublishedState]:
        if self._closed:
            return self._empty()

        subscriber = _Subscriber(
            queue=asyncio.Queue(maxsize=self._config.subscriber_queue_size)
        )
        self._subscribers.add(subscriber)
        return self._iter(subscriber)

    async def publish(self, item: PublishedState) -> None:
        if self._closed:
            return

        dead: list[_Subscriber] = []
        for subscriber in self._subscribers:
            try:
                subscriber.queue.put_nowait(item)
            except asyncio.QueueFull:
                policy = self._config.subscriber_overflow_policy
                if policy is SubscriberOverflowPolicy.DROP_OLDEST:
                    try:
                        _ = subscriber.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        subscriber.queue.put_nowait(item)
                    except asyncio.QueueFull as exc:
                        dead.append(subscriber)
                        raise SubscriptionOverflowError(
                            "subscriber queue remained full after dropping oldest item",
                            operation="broadcaster_publish",
                            cause=exc,
                        ) from exc
                else:
                    dead.append(subscriber)
                    raise SubscriptionOverflowError(
                        "subscriber queue overflowed",
                        operation="broadcaster_publish",
                    )

        for subscriber in dead:
            self._subscribers.discard(subscriber)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        for subscriber in tuple(self._subscribers):
            try:
                subscriber.queue.put_nowait(None)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueFull):
                    _ = subscriber.queue.get_nowait()
                    subscriber.queue.put_nowait(None)

        self._subscribers.clear()

    async def _iter(self, subscriber: _Subscriber) -> AsyncIterator[PublishedState]:
        try:
            while True:
                item = await subscriber.queue.get()
                if item is None:
                    return
                yield item
        finally:
            self._subscribers.discard(subscriber)

    async def _empty(self) -> AsyncIterator[PublishedState]:
        if False:
            yield  # pragma: no cover
        return
```

---

## `src/niri_state/resync.py`

```python id="820qg1"
from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from niri_state.config import NiriStateConfig, ResyncPolicy

if TYPE_CHECKING:
    from niri_state.store import NiriState


class ResyncCoordinator:
    def __init__(self, state: NiriState, config: NiriStateConfig) -> None:
        self._state = state
        self._config = config
        self._trigger = asyncio.Event()
        self._closed = False
        self._task: asyncio.Task[None] | None = None

        if config.resync_policy is ResyncPolicy.AUTO:
            self._task = asyncio.create_task(self._run())

    def request(self) -> None:
        if self._closed:
            return
        self._trigger.set()

    async def _run(self) -> None:
        while not self._closed:
            await self._trigger.wait()
            self._trigger.clear()

            if self._closed:
                return

            try:
                await self._state.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                continue

    async def close(self) -> None:
        self._closed = True
        self._trigger.set()

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
```

---

## `src/niri_state/store.py`

```python id="x8g6l8"
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from niri_state.bootstrap import run_bootstrap
from niri_state.broadcaster import Broadcaster, PublishedState
from niri_state.changes import (
    ChangedDomain,
    close_changeset,
    event_changeset,
    health_changeset,
    refresh_changeset,
)
from niri_state.config import InvariantFailurePolicy, NiriStateConfig, ResyncPolicy
from niri_state.diagnostics import InvariantViolation, with_error, with_invariant_violations, with_resync
from niri_state.engine_state import EngineState
from niri_state.errors import DesyncError, InvariantError, StateLifecycleError
from niri_state.health import HealthState, validate_transition
from niri_state.invariants import collect_invariant_violations
from niri_state.protocol import NiriConnectionBundle
from niri_state.reconcile import reconcile
from niri_state.reducers import reduce_event
from niri_state.resync import ResyncCoordinator
from niri_state.snapshot import Snapshot


class NiriState:
    def __init__(self, config: NiriStateConfig | None = None) -> None:
        self._config = config or NiriStateConfig()
        self._lock = asyncio.Lock()
        self._started = False
        self._closed = False

        self._bundle: NiriConnectionBundle | None = None
        self._engine: EngineState | None = None
        self._snapshot: Snapshot | None = None
        self._revision = 0

        self._mutation_task: asyncio.Task[None] | None = None
        self._broadcaster = Broadcaster(self._config)
        self._resync = ResyncCoordinator(self, self._config)

    async def _open_bundle(self) -> NiriConnectionBundle:
        return await NiriConnectionBundle.open(config=self._config.pypc)

    def snapshot(self) -> Snapshot:
        if self._snapshot is None:
            raise StateLifecycleError(
                "state has not been started",
                operation="snapshot",
            )
        return self._snapshot

    def health(self) -> HealthState:
        if self._engine is None:
            return HealthState.BOOTSTRAPPING
        return self._engine.health

    def subscribe(self) -> AsyncIterator[PublishedState]:
        return self._broadcaster.subscribe()

    async def connect(self) -> None:
        async with self._lock:
            if self._closed:
                raise StateLifecycleError(
                    "state is already closed",
                    operation="connect",
                )
            if self._started:
                raise StateLifecycleError(
                    "state is already started",
                    operation="connect",
                )

            self._bundle = await self._open_bundle()
            outcome = await run_bootstrap(self._bundle, config=self._config)

            self._engine = outcome.engine
            self._snapshot = outcome.initial_snapshot
            self._revision = outcome.initial_snapshot.revision

            await self._broadcaster.publish(
                PublishedState(
                    snapshot=outcome.initial_snapshot,
                    changes=outcome.initial_changeset,
                )
            )

            self._mutation_task = asyncio.create_task(self._mutation_loop())
            self._started = True

    async def start(self) -> NiriState:
        await self.connect()
        return self

    async def _mutation_loop(self) -> None:
        assert self._bundle is not None
        assert self._engine is not None

        async for event in self._bundle.events:
            if self._closed:
                return

            try:
                result = reduce_event(
                    self._engine,
                    event,
                    config=self._config,
                    revision=self._revision,
                )

                if not result.applied:
                    continue

                if result.marked_desync:
                    await self._transition_health(HealthState.STALE)

                reconcile(self._engine)

                self._revision += 1
                snapshot = self._engine.freeze(revision=self._revision)

                violations = collect_invariant_violations(snapshot)
                if violations:
                    snapshot = self._handle_invariant_violations(snapshot, violations)

                previous = self._snapshot
                self._snapshot = snapshot

                domains = result.domains
                if previous is not None and previous.health != snapshot.health:
                    domains = domains | frozenset(
                        {ChangedDomain.HEALTH, ChangedDomain.DIAGNOSTICS}
                    )

                await self._broadcaster.publish(
                    PublishedState(
                        snapshot=snapshot,
                        changes=event_changeset(
                            revision=snapshot.revision,
                            domains=domains,
                        ),
                    )
                )

            except DesyncError as exc:
                await self._mark_desynced(exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._fail(exc)
                raise

    def _handle_invariant_violations(
        self,
        snapshot: Snapshot,
        violations: tuple[InvariantViolation, ...],
    ) -> Snapshot:
        policy = self._config.invariant_failure_policy

        if policy is InvariantFailurePolicy.FAIL:
            raise InvariantError(
                "snapshot invariants violated",
                violations=violations,
                revision=snapshot.revision,
                operation="publish_snapshot",
            )

        assert self._engine is not None
        self._engine.diagnostics = with_invariant_violations(
            self._engine.diagnostics,
            violations=violations,
        )
        self._engine.health = HealthState.STALE
        reconcile(self._engine)
        return self._engine.freeze(revision=snapshot.revision, timestamp=snapshot.timestamp)

    async def _transition_health(self, target: HealthState) -> None:
        assert self._engine is not None
        current = self._engine.health
        if current == target:
            return
        validate_transition(current, target)
        self._engine.health = target

    async def _mark_desynced(self, exc: DesyncError) -> None:
        assert self._engine is not None

        self._engine.diagnostics = with_error(
            self._engine.diagnostics,
            message=str(exc),
        )
        await self._transition_health(HealthState.STALE)
        reconcile(self._engine)

        self._revision += 1
        snapshot = self._engine.freeze(revision=self._revision)
        self._snapshot = snapshot

        await self._broadcaster.publish(
            PublishedState(
                snapshot=snapshot,
                changes=health_changeset(revision=snapshot.revision),
            )
        )

        if self._config.resync_policy is ResyncPolicy.AUTO:
            self._resync.request()

    async def _fail(self, exc: Exception) -> None:
        assert self._engine is not None

        self._engine.diagnostics = with_error(
            self._engine.diagnostics,
            message=str(exc),
        )
        await self._transition_health(HealthState.FAILED)
        reconcile(self._engine)

        self._revision += 1
        snapshot = self._engine.freeze(revision=self._revision)
        self._snapshot = snapshot

        await self._broadcaster.publish(
            PublishedState(
                snapshot=snapshot,
                changes=health_changeset(revision=snapshot.revision),
            )
        )

    async def refresh(self) -> Snapshot:
        async with self._lock:
            if self._bundle is None:
                raise StateLifecycleError(
                    "state is not connected",
                    operation="refresh",
                )
            if self._closed:
                raise StateLifecycleError(
                    "state is already closed",
                    operation="refresh",
                )

            outcome = await run_bootstrap(self._bundle, config=self._config)
            self._engine = outcome.engine
            self._engine.diagnostics = with_resync(self._engine.diagnostics)
            self._engine.health = HealthState.LIVE

            self._revision += 1
            self._snapshot = self._engine.freeze(revision=self._revision)

            await self._broadcaster.publish(
                PublishedState(
                    snapshot=self._snapshot,
                    changes=refresh_changeset(
                        revision=self._snapshot.revision,
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
                    ),
                )
            )

            return self._snapshot

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return

            self._closed = True

            if self._mutation_task is not None:
                self._mutation_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._mutation_task

            if (
                self._engine is not None
                and self._engine.health not in {HealthState.CLOSED, HealthState.FAILED}
            ):
                await self._transition_health(HealthState.CLOSED)
                self._revision += 1
                self._snapshot = self._engine.freeze(revision=self._revision)

                await self._broadcaster.publish(
                    PublishedState(
                        snapshot=self._snapshot,
                        changes=close_changeset(revision=self._snapshot.revision),
                    )
                )

            if self._bundle is not None:
                await self._bundle.close()

            await self._resync.close()
            await self._broadcaster.close()
```

---

That is the consolidated runtime layer.

---


Part 3 of 3 — selectors, waiters, and consolidated test skeleton.

This finishes the package skeleton.

---

## `src/niri_state/selectors/__init__.py`

```python id="vav3qa"
from niri_state.selectors import (
    aggregates,
    focus,
    keyboard,
    outputs,
    overview,
    windows,
    workspaces,
)

__all__ = [
    "aggregates",
    "focus",
    "keyboard",
    "outputs",
    "overview",
    "windows",
    "workspaces",
]
```

---

## `src/niri_state/selectors/focus.py`

```python id="l6hr90"
from __future__ import annotations

from niri_state.protocol import Window, Workspace
from niri_state.snapshot import Snapshot


def get_focused_window_id(snapshot: Snapshot) -> int | None:
    return snapshot.focused_window_id


def get_focused_workspace_id(snapshot: Snapshot) -> int | None:
    return snapshot.focused_workspace_id


def get_focused_output_name(snapshot: Snapshot) -> str | None:
    return snapshot.focused_output_name


def get_focused_window(snapshot: Snapshot) -> Window | None:
    if snapshot.focused_window_id is None:
        return None
    return snapshot.windows.get(snapshot.focused_window_id)


def get_focused_workspace(snapshot: Snapshot) -> Workspace | None:
    if snapshot.focused_workspace_id is None:
        return None
    return snapshot.workspaces.get(snapshot.focused_workspace_id)
```

---

## `src/niri_state/selectors/outputs.py`

```python id="u0lcld"
from __future__ import annotations

from niri_state.protocol import Output, Workspace
from niri_state.snapshot import Snapshot


def get_output(snapshot: Snapshot, output_name: str) -> Output | None:
    return snapshot.outputs.get(output_name)


def list_outputs(snapshot: Snapshot) -> tuple[Output, ...]:
    return tuple(snapshot.outputs.values())


def get_workspaces_on_output(snapshot: Snapshot, output_name: str) -> tuple[Workspace, ...]:
    ids = snapshot.workspaces_by_output.get(output_name, ())
    return tuple(snapshot.workspaces[workspace_id] for workspace_id in ids)


def get_active_workspace_for_output(snapshot: Snapshot, output_name: str) -> Workspace | None:
    workspace_id = snapshot.active_workspace_by_output.get(output_name)
    if workspace_id is None:
        return None
    return snapshot.workspaces.get(workspace_id)
```

---

## `src/niri_state/selectors/workspaces.py`

```python id="c74iki"
from __future__ import annotations

from niri_state.protocol import Workspace
from niri_state.snapshot import Snapshot


def get_workspace(snapshot: Snapshot, workspace_id: int) -> Workspace | None:
    return snapshot.workspaces.get(workspace_id)


def list_workspaces(snapshot: Snapshot) -> tuple[Workspace, ...]:
    return tuple(snapshot.workspaces.values())


def list_workspaces_on_output(snapshot: Snapshot, output_name: str) -> tuple[Workspace, ...]:
    ids = snapshot.workspaces_by_output.get(output_name, ())
    return tuple(snapshot.workspaces[workspace_id] for workspace_id in ids)


def get_active_workspace(snapshot: Snapshot, output_name: str) -> Workspace | None:
    workspace_id = snapshot.active_workspace_by_output.get(output_name)
    if workspace_id is None:
        return None
    return snapshot.workspaces.get(workspace_id)
```

---

## `src/niri_state/selectors/windows.py`

```python id="nf7prr"
from __future__ import annotations

from niri_state.protocol import Window
from niri_state.snapshot import Snapshot


def get_window(snapshot: Snapshot, window_id: int) -> Window | None:
    return snapshot.windows.get(window_id)


def list_windows(snapshot: Snapshot) -> tuple[Window, ...]:
    return tuple(snapshot.windows.values())


def list_windows_on_workspace(snapshot: Snapshot, workspace_id: int) -> tuple[Window, ...]:
    ids = snapshot.windows_by_workspace.get(workspace_id, ())
    return tuple(snapshot.windows[window_id] for window_id in ids)


def list_floating_windows(snapshot: Snapshot) -> tuple[Window, ...]:
    return tuple(window for window in snapshot.windows.values() if window.is_floating)
```

---

## `src/niri_state/selectors/keyboard.py`

```python id="y0n3ta"
from __future__ import annotations

from niri_state.protocol import KeyboardLayouts
from niri_state.snapshot import Snapshot


def get_keyboard_layouts(snapshot: Snapshot) -> KeyboardLayouts:
    return snapshot.keyboard_layouts


def get_keyboard_current_name(snapshot: Snapshot) -> str | None:
    return snapshot.keyboard_current_name
```

---

## `src/niri_state/selectors/overview.py`

```python id="jlwmff"
from __future__ import annotations

from niri_state.protocol import Overview
from niri_state.snapshot import Snapshot


def get_overview(snapshot: Snapshot) -> Overview:
    return snapshot.overview


def is_overview_open(snapshot: Snapshot) -> bool:
    return snapshot.overview.is_open
```

---

## `src/niri_state/selectors/aggregates.py`

```python id="7crs78"
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from niri_state.protocol import Window, Workspace
from niri_state.snapshot import Snapshot


class FocusedContext(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    output_name: str | None
    workspace: Workspace | None
    window: Window | None


class WorkspaceTreeNode(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    workspace: Workspace
    windows: tuple[Window, ...]


def get_focused_context(snapshot: Snapshot) -> FocusedContext:
    workspace = None
    if snapshot.focused_workspace_id is not None:
        workspace = snapshot.workspaces.get(snapshot.focused_workspace_id)

    window = None
    if snapshot.focused_window_id is not None:
        window = snapshot.windows.get(snapshot.focused_window_id)

    return FocusedContext(
        output_name=snapshot.focused_output_name,
        workspace=workspace,
        window=window,
    )


def get_workspace_tree(snapshot: Snapshot, output_name: str) -> tuple[WorkspaceTreeNode, ...]:
    workspace_ids = snapshot.workspaces_by_output.get(output_name, ())
    nodes: list[WorkspaceTreeNode] = []

    for workspace_id in workspace_ids:
        workspace = snapshot.workspaces[workspace_id]
        window_ids = snapshot.windows_by_workspace.get(workspace_id, ())
        nodes.append(
            WorkspaceTreeNode(
                workspace=workspace,
                windows=tuple(snapshot.windows[window_id] for window_id in window_ids),
            )
        )

    return tuple(nodes)


def get_urgent_items(snapshot: Snapshot) -> tuple[Workspace | Window, ...]:
    items: list[Workspace | Window] = []
    items.extend(workspace for workspace in snapshot.workspaces.values() if workspace.is_urgent)
    items.extend(window for window in snapshot.windows.values() if window.is_urgent)
    return tuple(items)
```

---

## `src/niri_state/waiters.py`

```python id="knkk9k"
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Protocol, TypeVar

from niri_state.broadcaster import PublishedState
from niri_state.config import NiriStateConfig, WaitHealthPolicy
from niri_state.errors import WaitTimeoutError
from niri_state.health import HealthState
from niri_state.snapshot import Snapshot

T = TypeVar("T")


class WaitableState(Protocol):
    def snapshot(self) -> Snapshot: ...
    def subscribe(self) -> AsyncIterator[PublishedState]: ...


def _health_allows_wait(
    *,
    snapshot: Snapshot,
    config: NiriStateConfig,
) -> bool:
    if config.wait_health_policy is WaitHealthPolicy.ALLOW_STALE:
        return snapshot.health in {HealthState.LIVE, HealthState.STALE}
    return snapshot.health is HealthState.LIVE


async def _subscription_iter(state: WaitableState) -> AsyncIterator[Snapshot]:
    async for published in state.subscribe():
        yield published.snapshot


async def watch(state: WaitableState) -> AsyncIterator[Snapshot]:
    yield state.snapshot()
    async for snapshot in _subscription_iter(state):
        yield snapshot


async def wait_until(
    state: WaitableState,
    predicate: Callable[[Snapshot], bool],
    *,
    config: NiriStateConfig,
    timeout: float | None = None,
) -> Snapshot:
    current = state.snapshot()
    if _health_allows_wait(snapshot=current, config=config) and predicate(current):
        return current

    async def _wait() -> Snapshot:
        async for snapshot in _subscription_iter(state):
            if not _health_allows_wait(snapshot=snapshot, config=config):
                continue
            if predicate(snapshot):
                return snapshot
        raise WaitTimeoutError(
            "state subscription closed before predicate matched",
            timeout=timeout or 0.0,
            operation="wait_until",
        )

    try:
        if timeout is None:
            return await _wait()
        return await asyncio.wait_for(_wait(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise WaitTimeoutError(
            "timed out waiting for state predicate",
            timeout=timeout or 0.0,
            operation="wait_until",
            cause=exc,
        ) from exc


async def wait_for_selector(
    state: WaitableState,
    selector: Callable[[Snapshot], T],
    *,
    predicate: Callable[[T], bool] | None = None,
    config: NiriStateConfig,
    timeout: float | None = None,
) -> T:
    def _wrapped(snapshot: Snapshot) -> bool:
        value = selector(snapshot)
        if predicate is None:
            return bool(value)
        return predicate(value)

    snapshot = await wait_until(
        state,
        _wrapped,
        config=config,
        timeout=timeout,
    )
    return selector(snapshot)
```

---

## `tests/factories/__init__.py`

```python id="jjlwm8"
# Empty on purpose.
```

---

## `tests/factories/protocol.py`

```python id="vkpa14"
from __future__ import annotations

from pydantic import TypeAdapter

from niri_state.protocol import KeyboardLayouts, Output, Overview, Window, Workspace

_OUTPUT_ADAPTER = TypeAdapter(Output)
_WORKSPACE_ADAPTER = TypeAdapter(Workspace)
_WINDOW_ADAPTER = TypeAdapter(Window)
_KEYBOARD_ADAPTER = TypeAdapter(KeyboardLayouts)
_OVERVIEW_ADAPTER = TypeAdapter(Overview)


def make_output(**overrides: object) -> Output:
    payload = {
        "name": "HDMI-A-1",
        "make": "Dell",
        "model": "U2720Q",
        "physical_size": None,
        "scale": 1.0,
        "transform": "Normal",
        "mode": None,
        "current_workspace": None,
    }
    payload.update(overrides)
    return _OUTPUT_ADAPTER.validate_python(payload)


def make_workspace(**overrides: object) -> Workspace:
    payload = {
        "id": 1,
        "idx": 1,
        "name": None,
        "output": "HDMI-A-1",
        "is_active": True,
        "is_focused": True,
        "is_urgent": False,
        "active_window_id": None,
    }
    payload.update(overrides)
    return _WORKSPACE_ADAPTER.validate_python(payload)


def make_window(**overrides: object) -> Window:
    payload = {
        "id": 100,
        "title": "Terminal",
        "app_id": "foot",
        "pid": None,
        "workspace_id": 1,
        "is_focused": False,
        "is_floating": False,
        "is_urgent": False,
        "focus_timestamp": None,
        "layout": None,
    }
    payload.update(overrides)
    return _WINDOW_ADAPTER.validate_python(payload)


def make_keyboard_layouts(**overrides: object) -> KeyboardLayouts:
    payload = {
        "names": ["US", "DE"],
        "current_idx": 0,
    }
    payload.update(overrides)
    return _KEYBOARD_ADAPTER.validate_python(payload)


def make_overview(**overrides: object) -> Overview:
    payload = {
        "is_open": False,
    }
    payload.update(overrides)
    return _OVERVIEW_ADAPTER.validate_python(payload)
```

---

## `tests/factories/raw_frames.py`

```python id="mtyqjb"
from __future__ import annotations


def make_event_frame(payload: str) -> bytes:
    return payload.encode("utf-8")
```

---

## `tests/unit/test_config.py`

```python id="9b6n0f"
from __future__ import annotations

from niri_pypc import BackpressureMode

from niri_state.config import (
    InvariantFailurePolicy,
    SubscriberOverflowPolicy,
    UnknownEventPolicy,
    strict_config,
)


def test_strict_config_applies_fail_fast_policies() -> None:
    config = strict_config()

    assert config.pypc.backpressure_mode is BackpressureMode.FAIL_FAST
    assert config.unknown_event_policy is UnknownEventPolicy.FAIL
    assert config.invariant_failure_policy is InvariantFailurePolicy.FAIL
    assert config.subscriber_overflow_policy is SubscriberOverflowPolicy.FAIL_FAST
```

---

## `tests/unit/test_health.py`

```python id="i7s5m5"
from __future__ import annotations

import pytest

from niri_state.errors import StateLifecycleError
from niri_state.health import HealthState, validate_transition


def test_validate_transition_allows_live_to_stale() -> None:
    validate_transition(HealthState.LIVE, HealthState.STALE)


def test_validate_transition_rejects_closed_to_live() -> None:
    with pytest.raises(StateLifecycleError):
        validate_transition(HealthState.CLOSED, HealthState.LIVE)
```

---

## `tests/unit/test_diagnostics.py`

```python id="rz5c89"
from __future__ import annotations

from niri_state.diagnostics import Diagnostics, InvariantViolation, with_desync, with_invariant_violations


def test_with_desync_marks_diagnostic() -> None:
    diag = with_desync(Diagnostics(), event_type="UnknownEvent", reason="unknown event")
    assert diag.desynced is True
    assert diag.last_event_type == "UnknownEvent"
    assert diag.last_error == "unknown event"


def test_with_invariant_violations_stores_tuple() -> None:
    violations = (
        InvariantViolation(code="x", message="y"),
    )
    diag = with_invariant_violations(Diagnostics(), violations=violations)
    assert diag.invariant_violations == violations
```

---

## `tests/unit/test_snapshot.py`

```python id="hcyh59"
from __future__ import annotations

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.snapshot import Snapshot
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_output,
    make_overview,
    make_workspace,
)


def test_snapshot_derives_focused_output_name() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={"HDMI-A-1": make_output()},
        workspaces={1: make_workspace(id=1, output="HDMI-A-1")},
        windows={},
        focused_workspace_id=1,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.focused_output_name == "HDMI-A-1"


def test_snapshot_derives_keyboard_current_name() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(names=["US", "DE"], current_idx=1),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert snapshot.keyboard_current_name == "DE"
```

---

## `tests/unit/test_reconcile.py`

```python id="z6lthh"
from __future__ import annotations

from niri_state.engine_state import EngineState
from niri_state.reconcile import reconcile
from tests.factories.protocol import make_keyboard_layouts, make_overview, make_window, make_workspace


def test_reconcile_clears_missing_focused_window() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.focused_window_id = 999

    reconcile(engine)

    assert engine.focused_window_id is None


def test_reconcile_derives_focused_workspace_from_focused_window() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()
    engine.workspaces = {1: make_workspace(id=1)}
    engine.windows = {100: make_window(id=100, workspace_id=1)}
    engine.focused_window_id = 100

    reconcile(engine)

    assert engine.focused_workspace_id == 1
```

---

## `tests/unit/test_invariants.py`

```python id="y0kvfu"
from __future__ import annotations

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.invariants import collect_invariant_violations
from niri_state.snapshot import Snapshot
from tests.factories.protocol import (
    make_keyboard_layouts,
    make_output,
    make_overview,
    make_window,
)


def test_collects_missing_workspace_for_window() -> None:
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={"HDMI-A-1": make_output()},
        workspaces={},
        windows={100: make_window(id=100, workspace_id=99)},
        focused_workspace_id=None,
        focused_window_id=None,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    violations = collect_invariant_violations(snapshot)
    assert any(v.code == "window_workspace_missing" for v in violations)
```

---

## `tests/unit/test_reducers.py`

```python id="i942vu"
from __future__ import annotations

from niri_state.changes import ChangedDomain
from niri_state.engine_state import EngineState
from niri_state.reducers import reduce_windows_changed
from tests.factories.protocol import make_keyboard_layouts, make_overview, make_window


class _WindowsChangedEventStub:
    def __init__(self, windows):
        self.windows = windows


def test_reduce_windows_changed_replaces_windows() -> None:
    engine = EngineState.empty()
    engine.keyboard_layouts = make_keyboard_layouts()
    engine.overview = make_overview()

    event = _WindowsChangedEventStub(windows=[make_window(id=100), make_window(id=101)])
    domains = reduce_windows_changed(engine, event)

    assert set(engine.windows) == {100, 101}
    assert domains == frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})
```

---

## `tests/unit/test_selectors.py`

```python id="ld0b45"
from __future__ import annotations

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.selectors.focus import get_focused_window
from niri_state.snapshot import Snapshot
from tests.factories.protocol import make_keyboard_layouts, make_overview, make_window


def test_get_focused_window_returns_window() -> None:
    window = make_window(id=100)
    snapshot = Snapshot(
        revision=1,
        timestamp=0.0,
        health=HealthState.LIVE,
        outputs={},
        workspaces={},
        windows={100: window},
        focused_workspace_id=None,
        focused_window_id=100,
        keyboard_layouts=make_keyboard_layouts(),
        overview=make_overview(),
        diagnostics=Diagnostics(),
        compatibility=Compatibility(),
    )

    assert get_focused_window(snapshot) == window
```

---

## `tests/unit/test_broadcaster.py`

```python id="rdshiz"
from __future__ import annotations

import pytest

from niri_state.broadcaster import Broadcaster


@pytest.mark.asyncio
async def test_broadcaster_subscribe_returns_iterator() -> None:
    from niri_state.config import NiriStateConfig

    broadcaster = Broadcaster(NiriStateConfig())
    subscription = broadcaster.subscribe()
    assert subscription is not None
```

---

## `tests/unit/test_resync.py`

```python id="sr55zv"
from __future__ import annotations

import pytest

from niri_state.config import NiriStateConfig, ResyncPolicy
from niri_state.resync import ResyncCoordinator


class _DummyState:
    def __init__(self) -> None:
        self.refresh_count = 0

    async def refresh(self):
        self.refresh_count += 1


@pytest.mark.asyncio
async def test_resync_request_is_safe() -> None:
    state = _DummyState()
    coordinator = ResyncCoordinator(
        state,
        NiriStateConfig(resync_policy=ResyncPolicy.MANUAL),
    )
    coordinator.request()
    await coordinator.close()
```

---

## `tests/unit/test_waiters.py`

```python id="lwjlwm"
from __future__ import annotations

import pytest

from niri_state.config import NiriStateConfig
from niri_state.waiters import wait_until


@pytest.mark.asyncio
async def test_wait_until_returns_immediately_when_predicate_matches(dummy_state) -> None:
    snapshot = await wait_until(
        dummy_state,
        lambda s: True,
        config=NiriStateConfig(),
        timeout=0.1,
    )
    assert snapshot is dummy_state.snapshot()
```

---

## `tests/integration/test_bootstrap.py`

```python id="ji08hx"
from __future__ import annotations

import pytest

from niri_state.bootstrap import run_bootstrap
from niri_state.config import NiriStateConfig
from niri_state.health import HealthState


@pytest.mark.asyncio
async def test_run_bootstrap_builds_live_or_stale_snapshot(fake_bundle) -> None:
    outcome = await run_bootstrap(fake_bundle, config=NiriStateConfig())

    assert outcome.initial_snapshot.health in {HealthState.LIVE, HealthState.STALE}
    assert outcome.initial_snapshot.revision == 1
```

---

## `tests/integration/test_runtime_mutation_loop.py`

```python id="pqj9on"
from __future__ import annotations

import pytest

from niri_state.store import NiriState


@pytest.mark.asyncio
async def test_runtime_publishes_after_event(fake_runtime_bundle) -> None:
    state = NiriState()
    # TODO: monkeypatch state._open_bundle to return fake_runtime_bundle
    # await state.connect()
    # published = await anext(state.subscribe())
    # assert published.snapshot.revision >= 1
```

---

## `tests/integration/test_refresh.py`

```python id="lw1nif"
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_refresh_replaces_snapshot(fake_runtime_bundle) -> None:
    # TODO: implement using bundle seam in NiriState._open_bundle
    assert True
```

---

## `tests/integration/test_desync_and_auto_resync.py`

```python id="i7d23o"
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_auto_resync_requests_refresh(fake_runtime_bundle) -> None:
    # TODO: implement once fake bundle emits a desync-producing event path
    assert True
```

---

## `tests/integration/test_close_lifecycle.py`

```python id="tjddt5"
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_close_transitions_state(fake_runtime_bundle) -> None:
    # TODO: implement once runtime seam is wired
    assert True
```

---

## `tests/replay/test_replay_traces.py`

```python id="tzpo4j"
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_replay_trace_converges() -> None:
    # TODO: implement from saved typed event traces
    assert True
```

---

## Recommended first cleanup pass before real implementation

There are three places I would tighten immediately once you start coding against the real `niri-pypc` models:

1. `tests/factories/protocol.py`

   * align all payload keys exactly to the generated model fields.

2. `reducers.py`

   * replace any remaining implicit assumptions like `event.idx`, `event.layout`, `event.workspace_id`, `event.active_window_id` with exact upstream field names.

3. `bootstrap.py`

   * tighten `query_version()` to the exact version payload shape.

That is normal; the skeleton is intentionally architecture-first.

---

## Final recommendation on how to use this skeleton

I would now:

1. create a fresh branch,
2. add this new tree in parallel,
3. make the factories compile against the real upstream generated models,
4. get the state-layer unit tests green first,
5. then wire bootstrap,
6. then reducers,
7. then runtime,
8. then delete the legacy architecture.

This gives you the clean rewrite path without mixing old and new concerns.
