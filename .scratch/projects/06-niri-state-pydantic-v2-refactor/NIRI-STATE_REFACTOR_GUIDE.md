## Section 1 of 4 — target architecture, module tree, and core models

The governing rule is simple: **`niri-state` should store canonical `niri-pypc` models directly, and only add state-engine concerns on top**. The mutable reducer core should stay plain Python; the published snapshot and public config should be frozen Pydantic models. That split matches where Pydantic is strongest and avoids forcing validation machinery into the hot mutation path. Pydantic’s docs explicitly note that Pydantic dataclasses are not a replacement for Pydantic models, and that there are cases where `BaseModel` is the better choice. ([Pydantic Docs][1])

---

### 1. Package layout

```text
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

  bootstrap.py
  reducers.py
  store.py
  resync.py

  selectors/
    __init__.py
    focus.py
    outputs.py
    workspaces.py
    windows.py
    keyboard.py
    overview.py
    aggregates.py
```

What gets deleted from the current design:

* wrapper entity models
* bootstrap payload model
* split “draft vs snapshot builder vs wrapper entities” architecture
* stored derived indexes
* transport-style model abstractions inside `niri-state`

---

## 2. `protocol.py`

Purpose: define the only import boundary to `niri-pypc`.

Everything else in `niri-state` should import from this module, not from `niri_pypc.types.generated.*` directly.

```python
# src/niri_state/protocol.py
from __future__ import annotations

from niri_pypc import NiriClient, NiriConnectionBundle

from niri_pypc.types.generated.models import (
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    Workspace,
)

from niri_pypc.types.generated.event import (
    EventValue,
    UnknownEvent,
    ConfigLoadedEvent,
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

__all__ = [
    "NiriClient",
    "NiriConnectionBundle",
    "KeyboardLayouts",
    "Output",
    "Overview",
    "Window",
    "Workspace",
    "EventValue",
    "UnknownEvent",
    "ConfigLoadedEvent",
    "KeyboardLayoutsChangedEvent",
    "KeyboardLayoutSwitchedEvent",
    "OverviewOpenedOrClosedEvent",
    "ScreenshotCapturedEvent",
    "WindowClosedEvent",
    "WindowFocusChangedEvent",
    "WindowFocusTimestampChangedEvent",
    "WindowLayoutsChangedEvent",
    "WindowOpenedOrChangedEvent",
    "WindowsChangedEvent",
    "WindowUrgencyChangedEvent",
    "WorkspaceActivatedEvent",
    "WorkspaceActiveWindowChangedEvent",
    "WorkspacesChangedEvent",
    "WorkspaceUrgencyChangedEvent",
    "FocusedOutputRequest",
    "FocusedWindowRequest",
    "KeyboardLayoutsRequest",
    "OutputsRequest",
    "OverviewStateRequest",
    "VersionRequest",
    "WindowsRequest",
    "WorkspacesRequest",
    "FocusedOutputResponse",
    "FocusedWindowResponse",
    "KeyboardLayoutsResponse",
    "OutputsResponse",
    "OverviewStateResponse",
    "VersionResponse",
    "WindowsResponse",
    "WorkspacesResponse",
]
```

Design rule:

* this file is the only place allowed to know upstream generated import paths.

---

## 3. `config.py`

### Enums

```python
# src/niri_state/config.py
from __future__ import annotations

from enum import StrEnum

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
```

### Config model

I would remove `CorrectnessMode` entirely.

```python
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt
from niri_pypc import NiriConfig

class NiriStateConfig(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    pypc: NiriConfig = Field(default_factory=NiriConfig)

    unknown_event_policy: UnknownEventPolicy = UnknownEventPolicy.STALE
    invariant_failure_policy: InvariantFailurePolicy = InvariantFailurePolicy.STALE
    resync_policy: ResyncPolicy = ResyncPolicy.MANUAL
    wait_health_policy: WaitHealthPolicy = WaitHealthPolicy.LIVE_ONLY
    subscriber_overflow_policy: SubscriberOverflowPolicy = SubscriberOverflowPolicy.DROP_OLDEST

    subscriber_queue_size: PositiveInt = 64
    resync_max_attempts: PositiveInt = 3
    resync_backoff_base: PositiveFloat = 1.0
```

### Optional convenience constructor

```python
from niri_pypc import BackpressureMode

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

Important caution: Pydantic documents that `model_copy(update=...)` does **not** validate the update data, so it should only be used with trusted values. ([Pydantic Docs][2])

---

## 4. `health.py`

```python
# src/niri_state/health.py
from __future__ import annotations

from enum import StrEnum

class HealthState(StrEnum):
    BOOTSTRAPPING = "bootstrapping"
    LIVE = "live"
    STALE = "stale"
    RESYNCING = "resyncing"
    CLOSED = "closed"
    FAILED = "failed"
```

### Transition validator

```python
_ALLOWED_TRANSITIONS: dict[HealthState, frozenset[HealthState]] = {
    HealthState.BOOTSTRAPPING: frozenset({HealthState.LIVE, HealthState.FAILED, HealthState.CLOSED}),
    HealthState.LIVE: frozenset({HealthState.STALE, HealthState.RESYNCING, HealthState.CLOSED, HealthState.FAILED}),
    HealthState.STALE: frozenset({HealthState.RESYNCING, HealthState.CLOSED, HealthState.FAILED}),
    HealthState.RESYNCING: frozenset({HealthState.LIVE, HealthState.STALE, HealthState.CLOSED, HealthState.FAILED}),
    HealthState.CLOSED: frozenset(),
    HealthState.FAILED: frozenset(),
}

def validate_transition(current: HealthState, target: HealthState) -> None: ...
```

Signature:

```python
def validate_transition(current: HealthState, target: HealthState) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise StateLifecycleError(
            f"invalid health transition: {current} -> {target}",
            current_state=current,
            target_state=target,
            operation="health_transition",
        )
```

---

## 5. `diagnostics.py`

This file replaces the current scattering of diagnostics, compatibility, and invariant-state fragments.

```python
# src/niri_state/diagnostics.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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
```

Helper signatures:

```python
def with_event_applied(diag: Diagnostics, *, event_type: str) -> Diagnostics: ...
def with_desync(diag: Diagnostics, *, event_type: str, reason: str) -> Diagnostics: ...
def with_invariant_violations(
    diag: Diagnostics, *, violations: tuple[InvariantViolation, ...]
) -> Diagnostics: ...
def with_resync(diag: Diagnostics) -> Diagnostics: ...
def with_error(diag: Diagnostics, *, message: str) -> Diagnostics: ...
```

---

## 6. `changes.py`

```python
# src/niri_state/changes.py
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
```

Helper signatures:

```python
def bootstrap_changeset(*, revision: int) -> ChangeSet: ...
def event_changeset(*, revision: int, domains: frozenset[ChangedDomain]) -> ChangeSet: ...
def refresh_changeset(*, revision: int, domains: frozenset[ChangedDomain]) -> ChangeSet: ...
def health_changeset(*, revision: int) -> ChangeSet: ...
def close_changeset(*, revision: int) -> ChangeSet: ...
```

---

## 7. `snapshot.py`

This is the immutable, published state surface.

```python
# src/niri_state/snapshot.py
from __future__ import annotations

from functools import cached_property
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, field_validator

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.protocol import KeyboardLayouts, Output, Overview, Window, Workspace
```

### Snapshot model

```python
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
```

### Validators

```python
    @field_validator("outputs", "workspaces", "windows", mode="before")
    @classmethod
    def _freeze_mapping(cls, value: object) -> MappingProxyType:
        ...
```

Implementation:

```python
    @field_validator("outputs", "workspaces", "windows", mode="before")
    @classmethod
    def _freeze_mapping(cls, value: object) -> MappingProxyType:
        if isinstance(value, MappingProxyType):
            return value
        if isinstance(value, dict):
            return MappingProxyType(dict(value))
        raise TypeError(f"expected dict or MappingProxyType, got {type(value)!r}")
```

### Derived properties

I would start with `cached_property`, not `computed_field`. Pydantic’s current docs say `computed_field` is new in v2.13, while the `cached_property` path avoids pinning the design to that feature. ([Pydantic Docs][3])

```python
    @cached_property
    def focused_output_name(self) -> str | None:
        if self.focused_workspace_id is None:
            return None
        ws = self.workspaces.get(self.focused_workspace_id)
        return None if ws is None else ws.output

    @cached_property
    def workspaces_by_output(self) -> MappingProxyType[str, tuple[int, ...]]:
        buckets: dict[str, list[int]] = {}
        for workspace_id, ws in self.workspaces.items():
            buckets.setdefault(ws.output, []).append(workspace_id)
        return MappingProxyType({k: tuple(v) for k, v in buckets.items()})

    @cached_property
    def windows_by_workspace(self) -> MappingProxyType[int, tuple[int, ...]]:
        buckets: dict[int, list[int]] = {}
        for window_id, win in self.windows.items():
            if win.workspace_id is not None:
                buckets.setdefault(win.workspace_id, []).append(window_id)
        return MappingProxyType({k: tuple(v) for k, v in buckets.items()})

    @cached_property
    def active_workspace_by_output(self) -> MappingProxyType[str, int]:
        active: dict[str, int] = {}
        for workspace_id, ws in self.workspaces.items():
            if ws.is_active:
                active[ws.output] = workspace_id
        return MappingProxyType(active)

    @cached_property
    def keyboard_current_name(self) -> str | None:
        names = self.keyboard_layouts.names
        idx = self.keyboard_layouts.current_idx
        if 0 <= idx < len(names):
            return names[idx]
        return None
```

Important caution: Pydantic documents that `model_copy()` copies the underlying `__dict__`, which can have side effects if cached-property values live there. That is why I recommend **rebuilding** snapshots rather than repeatedly patching them with `model_copy()`. ([Pydantic Docs][2])

---

## 8. `engine_state.py`

This is the mutable internal state. Keep it plain.

```python
# src/niri_state/engine_state.py
from __future__ import annotations

from dataclasses import dataclass, field
from time import time

from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.health import HealthState
from niri_state.protocol import KeyboardLayouts, Output, Overview, Window, Workspace
from niri_state.snapshot import Snapshot
```

### Core class

```python
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
```

### Constructors / methods

```python
    @classmethod
    def empty(cls) -> "EngineState": ...

    def require_initialized(self) -> None: ...

    def freeze(self, *, revision: int, timestamp: float | None = None) -> Snapshot: ...
```

Suggested implementation contract:

```python
    @classmethod
    def empty(cls) -> "EngineState":
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

That is the core model layer.


[1]: https://docs.pydantic.dev/latest/concepts/dataclasses/ "Dataclasses | Pydantic Docs"
[2]: https://docs.pydantic.dev/latest/api/base_model/ "BaseModel | Pydantic Docs"
[3]: https://docs.pydantic.dev/latest/concepts/fields/ "Fields | Pydantic Docs"

---


## Section 2 of 4 — reconciliation, errors, and bootstrap

This section covers the part that makes the whole rewrite stable: **one reconciliation pass, a structured error taxonomy, and a typed bootstrap flow that treats `niri-pypc` as the canonical protocol client**.

The key architectural decision here is that reducers are allowed to be locally simple and even temporarily inconsistent, because `reconcile()` is the single place that restores canonical state relationships before publication. That is much cleaner than spreading focus/index repair logic across many reducers.

---

## 1. `reconcile.py`

This module should be small, explicit, and heavily tested.

Its job is to normalize the mutable `EngineState` after:

* bootstrap,
* any applied event,
* refresh,
* resync.

It should not know anything about subscriptions, broadcasting, or async runtime behavior.

### File shape

```python id="6wywkw"
# src/niri_state/reconcile.py
from __future__ import annotations

from niri_state.engine_state import EngineState
```

### Public entry point

```python id="e307d1"
def reconcile(engine: EngineState) -> None:
    _reconcile_focused_window(engine)
    _reconcile_focused_workspace(engine)
    _reconcile_keyboard(engine)
    _reconcile_workspace_window_relationships(engine)
    _reconcile_diagnostics(engine)
```

This should be intentionally imperative and easy to read.

---

## 2. Focus reconciliation rules

These are the canonical rules I would adopt.

### Focused window

If `focused_window_id` exists:

* the window must exist,
* if it does not, clear it,
* if it does, derive `focused_workspace_id` from the window when possible.

### Focused workspace

If `focused_workspace_id` exists:

* it must point to an existing workspace,
* otherwise clear it.

If `focused_workspace_id` is `None`:

* recover it from the first workspace whose protocol state says `is_focused=True`.

### Focused output

Do **not** store it on `EngineState`.
It is derived from the focused workspace.

That means no dedicated `_reconcile_focused_output()` function is needed.

### Suggested implementation

```python id="rpzclp"
def _reconcile_focused_window(engine: EngineState) -> None:
    if engine.focused_window_id is None:
        return

    win = engine.windows.get(engine.focused_window_id)
    if win is None:
        engine.focused_window_id = None
        return

    if win.workspace_id is not None:
        engine.focused_workspace_id = win.workspace_id
```

```python id="c6t4yy"
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
```

---

## 3. Workspace/window relationship reconciliation

This part is easy to get wrong if left implicit.

### Canonical rule

A `Window` whose `workspace_id` points to a missing workspace should not stay silently “valid”.

You have two possible designs:

* preserve it and report an invariant violation later,
* or aggressively drop it from engine state.

I recommend the first: **preserve the window, report the violation**.

Reason:

* the state engine should reflect what the compositor/protocol told us,
* diagnostics should record inconsistency,
* and aggressive deletion can hide real desync bugs.

So reconciliation should not mutate windows just to hide bad relationships.

It should only normalize pointers the state engine owns directly.

### Implementation

```python id="w1h3s2"
def _reconcile_workspace_window_relationships(engine: EngineState) -> None:
    # Intentionally a no-op for now.
    # Relationship validation belongs in invariants, not destructive reconciliation.
    return
```

That looks boring, but it is a deliberate separation of concerns.

---

## 4. Keyboard reconciliation

The keyboard protocol object is already canonical state.

There is very little to reconcile here.

If the current index is out of bounds, do **not** mutate the upstream model.
Just let the derived selector/property return `None`, and surface the oddity through invariants or diagnostics if desired.

So:

```python id="zn6lr3"
def _reconcile_keyboard(engine: EngineState) -> None:
    return
```

Again, intentionally boring.

---

## 5. Diagnostics reconciliation

This is a small but useful normalization point.

Examples:

* if invariant violations are now empty, clear any stale invariant-related note,
* if desync has been repaired via refresh/resync, clear or update specific diagnostic fields,
* preserve counters like `event_count` and `resync_count`.

I would keep this conservative.

```python id="k4j7wo"
def _reconcile_diagnostics(engine: EngineState) -> None:
    # Reserved for future normalization of state-local diagnostic fields.
    return
```

---

## 6. `errors.py`

The exception taxonomy should be structured, but still plain exceptions.

Do not turn errors into Pydantic models.

### File structure

```python id="ep0otm"
# src/niri_state/errors.py
from __future__ import annotations

from typing import Any

from niri_state.diagnostics import InvariantViolation
from niri_state.health import HealthState
```

### Base class

```python id="h38h39"
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
```

### Subclasses

```python id="rj7srd"
class StateConfigError(NiriStateError):
    pass
```

```python id="w04g84"
class StateLifecycleError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        current_state: HealthState | None = None,
        target_state: HealthState | None = None,
        operation: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(message, operation=operation, cause=cause)
```

```python id="r1j2zw"
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
        super().__init__(message, operation=operation, retryable=retryable, cause=cause)
```

```python id="uv0ihb"
class ReductionError(NiriStateError):
    def __init__(
        self,
        message: str,
        *,
        event_type: str | None = None,
        revision: int | None = None,
        operation: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.event_type = event_type
        self.revision = revision
        super().__init__(message, operation=operation, cause=cause)
```

```python id="oz5871"
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
        super().__init__(message, operation=operation)
```

```python id="e46hws"
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
        super().__init__(message, operation=operation, retryable=retryable, cause=cause)
```

```python id="ncefev"
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
    ) -> None:
        self.timeout = timeout
        super().__init__(message, operation=operation)
```

Design notes:

* keep them lightweight,
* add only fields that genuinely help call sites or logs,
* no elaborate inheritance tree beyond this.

---

## 7. `bootstrap.py`

This module should do exactly three things:

1. perform the initial typed queries,
2. start the event stream correctly,
3. build a canonical `EngineState` and initial `Snapshot`.

It should **not** contain a generic payload-unwrapping abstraction.
It should **not** use any internal bootstrap payload model.
It should **not** duplicate protocol parsing logic already owned by `niri-pypc`.

---

## 8. Bootstrap outcome model

This can be a small frozen `BaseModel`, because it is a public-ish orchestration result and not hot-path mutable state.

```python id="ohp5z0"
# src/niri_state/bootstrap.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from niri_state.changes import ChangeSet
from niri_state.snapshot import Snapshot

class BootstrapOutcome(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    initial_snapshot: Snapshot
    initial_changeset: ChangeSet
```

That is the only bootstrap result object I would keep.

---

## 9. Typed query helpers

Each helper should be tiny and explicit.

```python id="j60d0i"
from niri_state.protocol import (
    FocusedOutputRequest,
    FocusedWindowRequest,
    KeyboardLayoutsRequest,
    NiriClient,
    OutputsRequest,
    OverviewStateRequest,
    VersionRequest,
    WindowsRequest,
    WorkspacesRequest,
    KeyboardLayouts,
    Output,
    Overview,
    Window,
    Workspace,
)
```

### Helper signatures

```python id="ryk6nd"
async def query_outputs(client: NiriClient) -> dict[str, Output]: ...
async def query_workspaces(client: NiriClient) -> list[Workspace]: ...
async def query_windows(client: NiriClient) -> list[Window]: ...
async def query_focused_output(client: NiriClient) -> Output | None: ...
async def query_focused_window(client: NiriClient) -> Window | None: ...
async def query_keyboard_layouts(client: NiriClient) -> KeyboardLayouts: ...
async def query_overview(client: NiriClient) -> Overview: ...
async def query_version(client: NiriClient) -> str | None: ...
```

### Implementations

```python id="8vofxy"
async def query_outputs(client: NiriClient) -> dict[str, Output]:
    return (await client.request(OutputsRequest())).payload

async def query_workspaces(client: NiriClient) -> list[Workspace]:
    return (await client.request(WorkspacesRequest())).payload

async def query_windows(client: NiriClient) -> list[Window]:
    return (await client.request(WindowsRequest())).payload

async def query_focused_output(client: NiriClient) -> Output | None:
    return (await client.request(FocusedOutputRequest())).payload

async def query_focused_window(client: NiriClient) -> Window | None:
    return (await client.request(FocusedWindowRequest())).payload

async def query_keyboard_layouts(client: NiriClient) -> KeyboardLayouts:
    return (await client.request(KeyboardLayoutsRequest())).payload

async def query_overview(client: NiriClient) -> Overview:
    return (await client.request(OverviewStateRequest())).payload

async def query_version(client: NiriClient) -> str | None:
    return (await client.request(VersionRequest())).payload
```

This relies on `niri-pypc`’s typed request/response surface, which is exactly what we want.

---

## 10. Building the initial `EngineState`

This logic should be explicit, not hidden in an adapter object.

### Signature

```python id="0hcowr"
async def build_initial_engine_state(client: NiriClient) -> EngineState: ...
```

### Implementation outline

```python id="qih5ae"
from niri_state.diagnostics import Compatibility, Diagnostics
from niri_state.engine_state import EngineState
from niri_state.health import HealthState
from niri_state.reconcile import reconcile

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
    engine.workspaces = {ws.id: ws for ws in workspaces}
    engine.windows = {win.id: win for win in windows}
    engine.keyboard_layouts = keyboard_layouts
    engine.overview = overview
    engine.health = HealthState.BOOTSTRAPPING
    engine.compatibility = Compatibility(niri_version=version)
    engine.diagnostics = Diagnostics()

    engine.focused_window_id = None if focused_window is None else focused_window.id
    engine.focused_workspace_id = (
        None if focused_window is None else focused_window.workspace_id
    )

    if engine.focused_workspace_id is None:
        for ws_id, ws in engine.workspaces.items():
            if ws.is_focused:
                engine.focused_workspace_id = ws_id
                break

    reconcile(engine)
    return engine
```

### Note on focused output

I intentionally do not store `focused_output` itself or a dedicated `focused_output_name`.
The focused output query can still be used for diagnostics or validation if you want, but it should not define canonical state.

At most:

```python id="squ6s1"
if focused_output is not None and engine.focused_workspace_id is not None:
    ws = engine.workspaces.get(engine.focused_workspace_id)
    if ws is not None and ws.output != focused_output.name:
        engine.diagnostics = engine.diagnostics.model_copy(
            update={
                "notes": engine.diagnostics.notes + (
                    "focused_output query disagreed with focused workspace output",
                )
            }
        )
```

That keeps it as a compatibility/diagnostic check, not a primary state source.

---

## 11. Running bootstrap

### Signature

```python id="e06a50"
async def run_bootstrap(bundle: NiriConnectionBundle, *, config: NiriStateConfig) -> BootstrapOutcome: ...
```

### High-level flow

```python id="68txh8"
from niri_state.changes import ChangeCause, ChangeSet, ChangedDomain
from niri_state.config import NiriStateConfig
from niri_state.health import HealthState
from niri_state.protocol import NiriConnectionBundle

async def run_bootstrap(
    bundle: NiriConnectionBundle,
    *,
    config: NiriStateConfig,
) -> BootstrapOutcome:
    try:
        engine = await build_initial_engine_state(bundle.client)
        engine.health = HealthState.LIVE
        snapshot = engine.freeze(revision=1)
        changeset = ChangeSet(
            revision=1,
            cause=ChangeCause.BOOTSTRAP,
            domains=frozenset({
                ChangedDomain.OUTPUTS,
                ChangedDomain.WORKSPACES,
                ChangedDomain.WINDOWS,
                ChangedDomain.FOCUS,
                ChangedDomain.KEYBOARD,
                ChangedDomain.OVERVIEW,
                ChangedDomain.HEALTH,
                ChangedDomain.DIAGNOSTICS,
            }),
        )
        return BootstrapOutcome(
            initial_snapshot=snapshot,
            initial_changeset=changeset,
        )
    except Exception as exc:
        raise BootstrapError(
            "failed to bootstrap initial niri state",
            operation="bootstrap",
            retryable=True,
            cause=exc,
        ) from exc
```

---

## 12. Event-stream startup contract

This module does **not** need to manually model the handled handshake itself if `niri-pypc` already owns that contract.

That is a key design principle:

* `niri-state` should trust `niri-pypc` to establish the typed event stream correctly,
* and should only consume the resulting typed events.

So bootstrap should not re-implement event-stream wire protocol.

It should just depend on the already-open bundle and the event iterator it exposes.

---

## 13. Invariants at bootstrap time

After `build_initial_engine_state()` and `reconcile()`, run invariants before publishing the first snapshot.

Suggested helper:

```python id="6rzf74"
from niri_state.diagnostics import InvariantViolation

def collect_invariant_violations(engine: EngineState) -> tuple[InvariantViolation, ...]: ...
```

Bootstrap policy:

* if no violations: continue,
* if violations and policy is `STALE`: mark diagnostics, publish `LIVE` or `STALE` depending on how strict you want initial state to be,
* if violations and policy is `FAIL`: raise `InvariantError`.

I would actually recommend:

* bootstrap invariant failure under `STALE` => `STALE`
* bootstrap invariant failure under `FAIL` => exception

That gives a consistent story.

---

That is the bootstrap and reconciliation layer.

---


## Section 3 of 4 — reducers, invariants, and the runtime mutation loop

This section is the actual engine.

The design goal is:

* reducers stay small,
* all event typing comes from `niri-pypc`,
* local mutations are allowed to be temporarily incomplete,
* `reconcile()` repairs primary relationships,
* invariants validate the resulting canonical state,
* the store publishes exactly one new immutable snapshot per applied change.

That keeps the system easy to reason about.

---

## 1. `reducers.py`

This module should own:

* the typed event dispatch registry,
* one reducer per event family,
* unknown-event policy handling,
* the `reduce_event()` entry point.

It should **not**:

* publish snapshots,
* manage async queues,
* run subscriptions,
* do health transitions directly except through explicit result signals.

---

## 2. Core reducer types

```python id="a5h4mv"
# src/niri_state/reducers.py
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from niri_state.changes import ChangedDomain
from niri_state.config import NiriStateConfig, UnknownEventPolicy
from niri_state.diagnostics import Diagnostics
from niri_state.engine_state import EngineState
from niri_state.errors import DesyncError, ReductionError
from niri_state.protocol import (
    EventValue,
    UnknownEvent,
    ConfigLoadedEvent,
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
```

### Result model

```python id="qzv36y"
@dataclass(frozen=True, slots=True)
class ReduceResult:
    applied: bool
    domains: frozenset[ChangedDomain]
    marked_desync: bool = False
```

This is intentionally not a Pydantic model. It is a tiny internal return value.

### Reducer alias

```python id="n19ju4"
Reducer = Callable[[EngineState, object], frozenset[ChangedDomain]]
```

You can also type this more precisely with overloads, but I would keep it simple.

---

## 3. Dispatch registry

```python id="r1ck1q"
EVENT_REDUCERS: dict[type[EventValue], Reducer] = {}
```

Registration helper:

```python id="c34z0d"
def register(event_type: type[EventValue]) -> Callable[[Reducer], Reducer]:
    def decorator(fn: Reducer) -> Reducer:
        EVENT_REDUCERS[event_type] = fn
        return fn
    return decorator
```

This makes the file cleaner than constructing one giant dict literal.

---

## 4. `reduce_event()` entry point

This is the only reducer API the runtime should call.

### Signature

```python id="vjlwm0"
def reduce_event(
    engine: EngineState,
    event: EventValue,
    *,
    config: NiriStateConfig,
    revision: int,
) -> ReduceResult:
    ...
```

### High-level implementation

```python id="tvjlwm"
from niri_state.changes import ChangedDomain
from niri_state.diagnostics import with_desync, with_event_applied

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
```

That is the whole contract.

---

## 5. Domain assignment rules

Use consistent domain semantics across reducers.

### `ChangedDomain.OUTPUTS`

Used only when the outputs map changes.

### `ChangedDomain.WORKSPACES`

Used when workspace objects or workspace membership/state changes.

### `ChangedDomain.WINDOWS`

Used when window objects or window membership/state changes.

### `ChangedDomain.FOCUS`

Used when the user-visible focus context might change:

* focused window,
* focused workspace,
* active window on workspace,
* inferred focused output.

### `ChangedDomain.KEYBOARD`

Used when keyboard layouts or current index changes.

### `ChangedDomain.OVERVIEW`

Used when overview open/closed state changes.

### `ChangedDomain.DIAGNOSTICS`

Used when only diagnostics changed.

This is important because subscribers/selectors should be able to trust the meaning of a domain.

---

## 6. Window reducers

### `WindowsChangedEvent`

This is a full replacement event.

```python id="jflv4g"
@register(WindowsChangedEvent)
def reduce_windows_changed(
    engine: EngineState,
    event: WindowsChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.windows = {win.id: win for win in event.windows}
    return frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})
```

Reason for `FOCUS`: full replacement may invalidate focused window/workspace relationships.

### `WindowOpenedOrChangedEvent`

```python id="15p7kj"
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
```

### `WindowClosedEvent`

```python id="e7aehx"
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
```

### `WindowFocusChangedEvent`

```python id="4yfc4o"
@register(WindowFocusChangedEvent)
def reduce_window_focus_changed(
    engine: EngineState,
    event: WindowFocusChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.focused_window_id = None if event.id is None else event.id
    return frozenset({ChangedDomain.FOCUS})
```

### `WindowUrgencyChangedEvent`

```python id="mnszjn"
@register(WindowUrgencyChangedEvent)
def reduce_window_urgency_changed(
    engine: EngineState,
    event: WindowUrgencyChangedEvent,
) -> frozenset[ChangedDomain]:
    win = engine.windows.get(event.id)
    if win is None:
        raise DesyncError(
            "window urgency changed for unknown window",
            event_type=type(event).__name__,
            operation="reduce_window_urgency_changed",
        )
    engine.windows[event.id] = win.model_copy(update={"is_urgent": event.is_urgent})
    return frozenset({ChangedDomain.WINDOWS})
```

### `WindowFocusTimestampChangedEvent`

```python id="5952vx"
@register(WindowFocusTimestampChangedEvent)
def reduce_window_focus_timestamp_changed(
    engine: EngineState,
    event: WindowFocusTimestampChangedEvent,
) -> frozenset[ChangedDomain]:
    win = engine.windows.get(event.id)
    if win is None:
        raise DesyncError(
            "window focus timestamp changed for unknown window",
            event_type=type(event).__name__,
            operation="reduce_window_focus_timestamp_changed",
        )
    engine.windows[event.id] = win.model_copy(update={"focus_timestamp": event.focus_timestamp})
    return frozenset({ChangedDomain.WINDOWS, ChangedDomain.FOCUS})
```

### `WindowLayoutsChangedEvent`

```python id="sfg1j9"
@register(WindowLayoutsChangedEvent)
def reduce_window_layouts_changed(
    engine: EngineState,
    event: WindowLayoutsChangedEvent,
) -> frozenset[ChangedDomain]:
    win = engine.windows.get(event.id)
    if win is None:
        raise DesyncError(
            "window layouts changed for unknown window",
            event_type=type(event).__name__,
            operation="reduce_window_layouts_changed",
        )
    engine.windows[event.id] = win.model_copy(update={"layout": event.layout})
    return frozenset({ChangedDomain.WINDOWS})
```

---

## 7. Workspace reducers

### `WorkspacesChangedEvent`

```python id="1lbf6h"
@register(WorkspacesChangedEvent)
def reduce_workspaces_changed(
    engine: EngineState,
    event: WorkspacesChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.workspaces = {ws.id: ws for ws in event.workspaces}
    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})
```

### `WorkspaceActivatedEvent`

```python id="9t4sm6"
@register(WorkspaceActivatedEvent)
def reduce_workspace_activated(
    engine: EngineState,
    event: WorkspaceActivatedEvent,
) -> frozenset[ChangedDomain]:
    ws = engine.workspaces.get(event.id)
    if ws is None:
        raise DesyncError(
            "workspace activated for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_activated",
        )

    # clear existing active/focused workspace for the same output if needed
    updated: dict[int, object] = {}
    for workspace_id, existing in engine.workspaces.items():
        if existing.output != ws.output:
            continue
        if existing.is_active or existing.is_focused:
            updated[workspace_id] = existing.model_copy(
                update={"is_active": False, "is_focused": False}
            )

    engine.workspaces.update(updated)
    engine.workspaces[event.id] = ws.model_copy(update={"is_active": True, "is_focused": True})
    engine.focused_workspace_id = event.id

    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})
```

This reducer intentionally normalizes same-output active/focused semantics locally because it is easy and avoids transient ambiguity.

### `WorkspaceActiveWindowChangedEvent`

```python id="mhrfnk"
@register(WorkspaceActiveWindowChangedEvent)
def reduce_workspace_active_window_changed(
    engine: EngineState,
    event: WorkspaceActiveWindowChangedEvent,
) -> frozenset[ChangedDomain]:
    ws = engine.workspaces.get(event.workspace_id)
    if ws is None:
        raise DesyncError(
            "workspace active window changed for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_active_window_changed",
        )
    engine.workspaces[event.workspace_id] = ws.model_copy(
        update={"active_window_id": event.active_window_id}
    )
    return frozenset({ChangedDomain.WORKSPACES, ChangedDomain.FOCUS})
```

### `WorkspaceUrgencyChangedEvent`

```python id="s8br77"
@register(WorkspaceUrgencyChangedEvent)
def reduce_workspace_urgency_changed(
    engine: EngineState,
    event: WorkspaceUrgencyChangedEvent,
) -> frozenset[ChangedDomain]:
    ws = engine.workspaces.get(event.id)
    if ws is None:
        raise DesyncError(
            "workspace urgency changed for unknown workspace",
            event_type=type(event).__name__,
            operation="reduce_workspace_urgency_changed",
        )
    engine.workspaces[event.id] = ws.model_copy(update={"is_urgent": event.is_urgent})
    return frozenset({ChangedDomain.WORKSPACES})
```

---

## 8. Keyboard and overview reducers

### `KeyboardLayoutsChangedEvent`

```python id="klq0qk"
@register(KeyboardLayoutsChangedEvent)
def reduce_keyboard_layouts_changed(
    engine: EngineState,
    event: KeyboardLayoutsChangedEvent,
) -> frozenset[ChangedDomain]:
    engine.keyboard_layouts = event.keyboard_layouts
    return frozenset({ChangedDomain.KEYBOARD})
```

### `KeyboardLayoutSwitchedEvent`

```python id="qk1zy8"
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
```

This is a deliberate correction to the current “compare only current_name” style of logic. The protocol object changes, so the state changed.

### `OverviewOpenedOrClosedEvent`

```python id="ou294k"
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
```

---

## 9. Ignored or diagnostic-only events

Some events do not affect state.

### `ConfigLoadedEvent`

This is a valid event, but I would not treat it as canonical state.

```python id="uzd1nu"
@register(ConfigLoadedEvent)
def reduce_config_loaded(
    engine: EngineState,
    event: ConfigLoadedEvent,
) -> frozenset[ChangedDomain]:
    return frozenset()
```

### `ScreenshotCapturedEvent`

Likewise, not part of compositor state snapshot.

```python id="vmwgd4"
@register(ScreenshotCapturedEvent)
def reduce_screenshot_captured(
    engine: EngineState,
    event: ScreenshotCapturedEvent,
) -> frozenset[ChangedDomain]:
    return frozenset()
```

A zero-domain applied reducer is perfectly acceptable.

---

## 10. Unknown event policy

This logic should live near `reduce_event()`, not in the store.

### Signature

```python id="7kjz3u"
def _handle_unknown_event(
    engine: EngineState,
    event: EventValue,
    *,
    config: NiriStateConfig,
    revision: int,
) -> ReduceResult:
    ...
```

### Implementation

```python id="bkm38e"
from niri_state.changes import ChangedDomain
from niri_state.diagnostics import with_desync, with_error

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

This keeps the policy logic compact and transparent.

---

## 11. `invariants.py`

This module should validate **published canonical state**, not random intermediate mutation phases.

That means it should operate on `Snapshot` or on a fully reconciled `EngineState`.

I recommend validating `Snapshot`, because that makes the public contract explicit.

### File structure

```python id="uobca4"
# src/niri_state/invariants.py
from __future__ import annotations

from niri_state.diagnostics import InvariantViolation
from niri_state.snapshot import Snapshot
```

### Public API

```python id="hzznln"
def collect_invariant_violations(snapshot: Snapshot) -> tuple[InvariantViolation, ...]: ...
def assert_invariants(snapshot: Snapshot) -> None: ...
```

### Implementation outline

```python id="yryx3c"
from niri_state.errors import InvariantError

def collect_invariant_violations(snapshot: Snapshot) -> tuple[InvariantViolation, ...]:
    violations: list[InvariantViolation] = []

    # focused window must exist
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

    # focused workspace must exist
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

    # window.workspace_id must reference existing workspace when not None
    for window_id, win in snapshot.windows.items():
        if win.workspace_id is not None and win.workspace_id not in snapshot.workspaces:
            violations.append(
                InvariantViolation(
                    code="window_workspace_missing",
                    message="window references missing workspace",
                    path=("windows", window_id, "workspace_id"),
                )
            )

    # workspace.output must reference existing output
    for workspace_id, ws in snapshot.workspaces.items():
        if ws.output not in snapshot.outputs:
            violations.append(
                InvariantViolation(
                    code="workspace_output_missing",
                    message="workspace references missing output",
                    path=("workspaces", workspace_id, "output"),
                )
            )

    # active workspace map must be coherent with workspaces
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
```

### Assertion helper

```python id="93t380"
def assert_invariants(snapshot: Snapshot) -> None:
    violations = collect_invariant_violations(snapshot)
    if violations:
        raise InvariantError(
            "snapshot invariants violated",
            violations=violations,
            revision=snapshot.revision,
            operation="assert_invariants",
        )
```

---

## 12. `store.py`

This is the runtime engine.

It should own:

* lifecycle,
* bootstrap,
* event consumption,
* reconciliation,
* snapshot freezing,
* invariant enforcement,
* publication to subscribers.

It should **not** contain detailed reducer logic.

---

## 13. Store structure

```python id="jv9t2u"
# src/niri_state/store.py
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from niri_state.bootstrap import run_bootstrap
from niri_state.changes import (
    ChangeCause,
    ChangeSet,
    ChangedDomain,
    close_changeset,
    event_changeset,
    health_changeset,
    refresh_changeset,
)
from niri_state.config import InvariantFailurePolicy, NiriStateConfig
from niri_state.diagnostics import with_error, with_invariant_violations, with_resync
from niri_state.engine_state import EngineState
from niri_state.errors import DesyncError, StateLifecycleError
from niri_state.health import HealthState, validate_transition
from niri_state.invariants import collect_invariant_violations
from niri_state.reconcile import reconcile
from niri_state.reducers import reduce_event
from niri_state.snapshot import Snapshot
```

---

## 14. Broadcaster contract

I would keep the broadcaster concept, but simplify the payload.

Subscribers should receive:

```python id="iy6p4r"
tuple[Snapshot, ChangeSet]
```

If you prefer readability, define:

```python id="lwvm5w"
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class PublishedState:
    snapshot: Snapshot
    changes: ChangeSet
```

I think the dataclass wrapper is cleaner.

---

## 15. `NiriState` core API

```python id="r6rkgf"
class NiriState:
    def __init__(self, config: NiriStateConfig | None = None) -> None: ...
    async def connect(self) -> None: ...
    def snapshot(self) -> Snapshot: ...
    def health(self) -> HealthState: ...
    def subscribe(self) -> AsyncIterator[PublishedState]: ...
    async def refresh(self) -> Snapshot: ...
    async def close(self) -> None: ...
```

That is the full public store API I would target.

---

## 16. Runtime fields

```python id="3f0p1n"
class NiriState:
    def __init__(self, config: NiriStateConfig | None = None) -> None:
        self._config = config or NiriStateConfig()
        self._lock = asyncio.Lock()
        self._started = False
        self._closed = False

        self._bundle = None
        self._engine: EngineState | None = None
        self._snapshot: Snapshot | None = None
        self._revision = 0

        self._mutation_task: asyncio.Task[None] | None = None
        self._broadcaster = Broadcaster(config=self._config)
        self._resync = ResyncCoordinator(self)
```

I would keep a single mutation task and a single mutable engine state.

---

## 17. `connect()`

### High-level flow

```python id="8j9x6m"
async def connect(self) -> None:
    async with self._lock:
        if self._started:
            raise StateLifecycleError(
                "state already started",
                operation="connect",
            )

        self._bundle = await NiriConnectionBundle.open(config=self._config.pypc)
        outcome = await run_bootstrap(self._bundle, config=self._config)

        self._snapshot = outcome.initial_snapshot
        self._revision = outcome.initial_snapshot.revision
        self._engine = await build_initial_engine_state(self._bundle.client)
        self._engine.health = HealthState.LIVE

        await self._broadcaster.publish(
            PublishedState(
                snapshot=outcome.initial_snapshot,
                changes=outcome.initial_changeset,
            )
        )

        self._mutation_task = asyncio.create_task(self._mutation_loop())
        self._started = True
```

You can also have `run_bootstrap()` return both the engine and snapshot if you want to avoid rebuilding the engine twice. That is probably the better design.

So I would actually change `BootstrapOutcome` to:

```python id="4z2h6m"
class BootstrapOutcome(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    engine: EngineState
    initial_snapshot: Snapshot
    initial_changeset: ChangeSet
```

Since `EngineState` is not a Pydantic model, you would need `arbitrary_types_allowed=True`. That is acceptable for this narrow orchestration object.

---

## 18. `_mutation_loop()`

This is the most important runtime function.

### Signature

```python id="o7d66b"
async def _mutation_loop(self) -> None: ...
```

### Flow

```python id="l78jzh"
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

            self._snapshot = snapshot

            await self._broadcaster.publish(
                PublishedState(
                    snapshot=snapshot,
                    changes=event_changeset(
                        revision=snapshot.revision,
                        domains=result.domains | _health_domain_if_changed(snapshot),
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
```

This is the core story of the runtime.

---

## 19. Handling invariant violations in the store

I would centralize invariant policy here.

### Signature

```python id="2v4m8f"
def _handle_invariant_violations(
    self,
    snapshot: Snapshot,
    violations: tuple[InvariantViolation, ...],
) -> Snapshot:
    ...
```

### Implementation

```python id="7r0ucx"
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
    return self._engine.freeze(revision=snapshot.revision)
```

The store owns this policy because it owns publication.

---

## 20. Health transitions

The runtime should own explicit health transitions in one place.

```python id="o42xgm"
async def _transition_health(self, target: HealthState) -> None:
    assert self._engine is not None
    current = self._engine.health
    if current == target:
        return
    validate_transition(current, target)
    self._engine.health = target
```

No implicit health updates outside store/resync/bootstrap.

---

## 21. `_mark_desynced()` and `_fail()`

```python id="rjlwv7"
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
```

```python id="8m2e7l"
async def _fail(self, exc: Exception) -> None:
    assert self._engine is not None

    self._engine.diagnostics = with_error(
        self._engine.diagnostics,
        message=str(exc),
    )
    await self._transition_health(HealthState.FAILED)
    reconcile(self._engine)

    self._revision += 1
    self._snapshot = self._engine.freeze(revision=self._revision)

    await self._broadcaster.publish(
        PublishedState(
            snapshot=self._snapshot,
            changes=health_changeset(revision=self._snapshot.revision),
        )
    )
```

---

## 22. `refresh()`

`refresh()` should do a full typed re-bootstrap and replace canonical engine state.

### Signature

```python id="8yqr3u"
async def refresh(self) -> Snapshot: ...
```

### Implementation outline

```python id="1mh86w"
async def refresh(self) -> Snapshot:
    async with self._lock:
        if self._bundle is None:
            raise StateLifecycleError("state is not connected", operation="refresh")

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
                    domains=frozenset({
                        ChangedDomain.OUTPUTS,
                        ChangedDomain.WORKSPACES,
                        ChangedDomain.WINDOWS,
                        ChangedDomain.FOCUS,
                        ChangedDomain.KEYBOARD,
                        ChangedDomain.OVERVIEW,
                        ChangedDomain.HEALTH,
                        ChangedDomain.DIAGNOSTICS,
                    }),
                ),
            )
        )
        return self._snapshot
```

I would not try to diff the refreshed bootstrap against previous state. A full refresh is semantically a full re-sync.

---

## 23. `close()`

```python id="g5mgsd"
async def close(self) -> None:
    async with self._lock:
        if self._closed:
            return
        self._closed = True

        if self._mutation_task is not None:
            self._mutation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._mutation_task

        if self._engine is not None and self._engine.health not in {HealthState.CLOSED, HealthState.FAILED}:
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

        await self._broadcaster.close()
```

---

## 24. Why this runtime model is cleaner

This design gives you:

* a single mutable source of truth,
* exactly one reconciliation point,
* exactly one invariant check point,
* exactly one publication point,
* no duplicate domain modeling layer,
* no ad hoc state patching spread across reducers and runtime.

That is the essence of the rewrite.


---

## Section 4 of 4 — selectors, resync, broadcaster, tests, and execution plan

This is the last piece: the surface area users interact with, the resync policy, and the concrete order I would build and land the rewrite.

The main principle for everything in this section is the same as the rest of the design:

* keep the public surface small,
* make selectors read directly from canonical snapshot state,
* keep resync logic outside reducers,
* make tests describe behavior, not implementation details.

---

## 1. `selectors/`

Selectors should be tiny, direct, and boring.

That is a feature.

They should operate on `Snapshot` and return upstream protocol models or simple derived values. No wrapper objects, no `.protocol`, no extra view-model layer.

---

## 2. `selectors/focus.py`

```python id="arznmk"
# src/niri_state/selectors/focus.py
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

That is all this module should do.

---

## 3. `selectors/outputs.py`

```python id="1v7d8w"
# src/niri_state/selectors/outputs.py
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

## 4. `selectors/workspaces.py`

```python id="eo8msm"
# src/niri_state/selectors/workspaces.py
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

## 5. `selectors/windows.py`

```python id="ln72th"
# src/niri_state/selectors/windows.py
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
    return tuple(win for win in snapshot.windows.values() if win.is_floating)
```

---

## 6. `selectors/keyboard.py`

```python id="sgn0rf"
# src/niri_state/selectors/keyboard.py
from __future__ import annotations

from niri_state.protocol import KeyboardLayouts
from niri_state.snapshot import Snapshot

def get_keyboard_layouts(snapshot: Snapshot) -> KeyboardLayouts:
    return snapshot.keyboard_layouts

def get_keyboard_current_name(snapshot: Snapshot) -> str | None:
    return snapshot.keyboard_current_name
```

---

## 7. `selectors/overview.py`

```python id="x4c3xy"
# src/niri_state/selectors/overview.py
from __future__ import annotations

from niri_state.protocol import Overview
from niri_state.snapshot import Snapshot

def get_overview(snapshot: Snapshot) -> Overview:
    return snapshot.overview

def is_overview_open(snapshot: Snapshot) -> bool:
    return snapshot.overview.is_open
```

---

## 8. `selectors/aggregates.py`

This is the only selector module that should do slightly richer composition.

I would keep it limited to things that are genuinely useful and can be expressed as simple data.

```python id="mfro0v"
# src/niri_state/selectors/aggregates.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from niri_state.protocol import Window, Workspace
from niri_state.snapshot import Snapshot
```

### Aggregate models

```python id="qqs8is"
class FocusedContext(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    output_name: str | None
    workspace: Workspace | None
    window: Window | None

class WorkspaceTreeNode(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    workspace: Workspace
    windows: tuple[Window, ...]
```

### Aggregate selectors

```python id="3mr7gt"
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
    items.extend(ws for ws in snapshot.workspaces.values() if ws.is_urgent)
    items.extend(win for win in snapshot.windows.values() if win.is_urgent)
    return tuple(items)
```

That is the upper limit of selector complexity I would permit.

---

## 9. `resync.py`

Resync should stay as a separate coordinator object, but I would simplify it.

Its responsibilities:

* know whether resync is allowed,
* queue or coalesce resync requests,
* call `state.refresh()` when appropriate,
* avoid duplicate concurrent refreshes.

It should **not**:

* know reducer details,
* mutate engine state directly,
* publish snapshots itself.

### File structure

```python id="9g9vl4"
# src/niri_state/resync.py
from __future__ import annotations

import asyncio

from niri_state.config import NiriStateConfig, ResyncPolicy
```

### Contract

```python id="k9k64c"
class ResyncCoordinator:
    def __init__(self, state: "NiriState", config: NiriStateConfig) -> None: ...
    def request(self) -> None: ...
    async def close(self) -> None: ...
```

### Suggested implementation

```python id="wjrjmn"
class ResyncCoordinator:
    def __init__(self, state: "NiriState", config: NiriStateConfig) -> None:
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
                # Intentionally swallow here; diagnostics/health are handled by state.refresh()
                continue

    async def close(self) -> None:
        self._closed = True
        self._trigger.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
```

This is deliberately simpler than a backoff-heavy coordinator.
If you later want backoff, add it here and nowhere else.

---

## 10. `Broadcaster`

I would keep the broadcaster abstraction, but I would make it lean and explicit.

### Public publication type

```python id="smmn51"
from dataclasses import dataclass

from niri_state.changes import ChangeSet
from niri_state.snapshot import Snapshot

@dataclass(frozen=True, slots=True)
class PublishedState:
    snapshot: Snapshot
    changes: ChangeSet
```

### Broadcaster contract

```python id="uq92b9"
class Broadcaster:
    def __init__(self, config: NiriStateConfig) -> None: ...
    def subscribe(self) -> AsyncIterator[PublishedState]: ...
    async def publish(self, item: PublishedState) -> None: ...
    async def close(self) -> None: ...
```

### Queue policy behavior

* `DROP_OLDEST`: pop one item then enqueue the new one
* `FAIL_FAST`: raise `SubscriptionOverflowError`

That is enough.

I would **not** add replay buffers, last-value caches, or filter subscriptions in the first rewrite. Keep it sharp.

---

## 11. `__init__.py`

The public package surface should be intentionally small.

```python id="wdjlwm"
from niri_state.config import (
    InvariantFailurePolicy,
    NiriStateConfig,
    ResyncPolicy,
    SubscriberOverflowPolicy,
    UnknownEventPolicy,
    WaitHealthPolicy,
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
from niri_state.store import NiriState
from niri_state.snapshot import Snapshot
from niri_state.changes import ChangeCause, ChangeSet, ChangedDomain
```

That should be the core export surface.

Do **not** export low-level engine internals.

---

## 12. Test plan

The tests should be rewritten around behavior, not around the old object graph.

### Test tree

```text id="jlwm7o"
tests/
  factories/
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

## 13. Protocol factories

This is one of the most important improvements.

All test construction of protocol models should go through shared factories.

### `tests/factories/protocol.py`

```python id="vhtalz"
from __future__ import annotations

from functools import lru_cache
from pydantic import TypeAdapter

from niri_state.protocol import KeyboardLayouts, Output, Overview, Window, Workspace
```

Use cached `TypeAdapter`s where fixture parsing from dicts is useful. Pydantic’s performance docs recommend instantiating a `TypeAdapter` once and reusing it, because each instantiation constructs validators and serializers. ([docs.pydantic.dev](https://docs.pydantic.dev/latest/concepts/performance/))

```python id="ffzdu0"
_OUTPUT_ADAPTER = TypeAdapter(Output)
_WORKSPACE_ADAPTER = TypeAdapter(Workspace)
_WINDOW_ADAPTER = TypeAdapter(Window)
_KEYBOARD_ADAPTER = TypeAdapter(KeyboardLayouts)
_OVERVIEW_ADAPTER = TypeAdapter(Overview)
```

Then:

```python id="wwg1nu"
def make_output(**overrides: object) -> Output: ...
def make_workspace(**overrides: object) -> Workspace: ...
def make_window(**overrides: object) -> Window: ...
def make_keyboard_layouts(**overrides: object) -> KeyboardLayouts: ...
def make_overview(**overrides: object) -> Overview: ...
```

These factories should produce valid modern protocol shapes only.
No stale fields from older generated schemas.

---

## 14. Core unit tests

### `test_snapshot.py`

Test:

* mapping freezing,
* derived properties,
* focused output derivation,
* active workspace derivation,
* keyboard current name derivation.

### `test_reconcile.py`

This is one of the most important modules.
Test:

* focused window removed -> focused window cleared,
* focused window implies focused workspace,
* missing focused workspace recovered from `is_focused`,
* stale workspace pointer cleared,
* no destructive cleanup of bad window/workspace relations.

### `test_invariants.py`

Test:

* missing focused window,
* missing focused workspace,
* window points to missing workspace,
* workspace points to missing output,
* invalid active workspace map.

### `test_reducers.py`

One test per event reducer:

* state mutation,
* changed domains,
* desync behavior for unknown entities.

### `test_selectors.py`

Selectors should be almost trivial to test.

---

## 15. Integration tests

### `test_bootstrap.py`

Use a mock `niri-pypc` bundle/client surface or a test double that returns typed replies.

Test:

* initial state construction,
* focused window/workspace derivation,
* diagnostics population,
* invariant policy during bootstrap.

### `test_runtime_mutation_loop.py`

Feed typed events into the runtime and assert:

* revision increments,
* one publication per applied mutation,
* domains are correct,
* state matches expectation after reconciliation.

### `test_refresh.py`

Assert:

* refresh replaces canonical state,
* revision increments,
* diagnostics resync count increments,
* health returns to `LIVE`.

### `test_desync_and_auto_resync.py`

Assert:

* desync transitions health to `STALE`,
* diagnostics update,
* auto resync requests a refresh.

### `test_close_lifecycle.py`

Assert:

* close cancels mutation loop,
* health becomes `CLOSED`,
* subscribers are closed.

---

## 16. Replay tests

I would keep replay tests, but rewrite them around the new public model.

### `tests/replay/test_replay_traces.py`

The contract should be:

* start from a bootstrap state,
* replay a sequence of typed events,
* compare final `Snapshot` against an expected snapshot.

This is a very strong test style for a deterministic state engine.

If you ever need to load raw JSON frames, use `model_validate_json()` or cached adapters at the test boundary instead of hand-parsing repeatedly. Pydantic’s performance docs recommend `model_validate_json()` in general over `json.loads(...)` followed by validation. ([docs.pydantic.dev](https://docs.pydantic.dev/latest/concepts/performance/))

---

## 17. Migration sequence

This is the exact sequence I would use.

### Commit 1 — lay down the new foundation

Create:

* `protocol.py`
* `config.py`
* `health.py`
* `diagnostics.py`
* `changes.py`
* `snapshot.py`
* `engine_state.py`
* `reconcile.py`

Add:

* unit tests for config, snapshot, reconcile, diagnostics, health.

Do not touch runtime yet.

### Commit 2 — add invariants

Create:

* `invariants.py`

Add:

* invariant unit tests.

### Commit 3 — add reducers

Create:

* `reducers.py`

Add:

* reducer unit tests for every event type.

### Commit 4 — add bootstrap

Create:

* `bootstrap.py`

Add:

* bootstrap integration tests.

### Commit 5 — add broadcaster and resync

Create:

* broadcaster implementation,
* `resync.py`.

Add:

* broadcaster and resync unit tests.

### Commit 6 — add store/runtime

Create:

* `store.py`

Add:

* runtime mutation loop tests,
* refresh tests,
* close lifecycle tests.

### Commit 7 — add selectors

Create:

* all selector modules

Add:

* selector tests.

### Commit 8 — add replay harness

Create:

* replay tests and trace helpers.

### Commit 9 — switch package exports

Update:

* `__init__.py`
* docs / README

### Commit 10 — delete legacy architecture

Remove:

* wrapper entity models
* old reducers
* old runtime/store/bootstrap tree
* any compatibility scaffolding

That last commit should be massive, but satisfying.

---

## 18. First concrete implementation steps

If I were starting right now, I would do these exact first steps:

### Step 1

Implement `protocol.py`, `health.py`, `diagnostics.py`, `changes.py`.

### Step 2

Implement `Snapshot` and `EngineState`.

### Step 3

Write tests for:

* `Snapshot.focused_output_name`
* `Snapshot.workspaces_by_output`
* `Snapshot.windows_by_workspace`
* `Snapshot.keyboard_current_name`

### Step 4

Implement `reconcile()` and write the reconciliation tests.

### Step 5

Implement `invariants.py` and write invariant tests.

Only after that would I touch bootstrap and reducers.

That order matters because it forces the state model to become crisp before runtime complexity arrives.

---

## 19. What I would explicitly not do

I would not:

* port old tests first,
* preserve wrapper compatibility,
* refactor in place file-by-file within the legacy tree,
* introduce internal `ProtocolModel` abstractions,
* overuse `computed_field`,
* build a fancy resync backoff system before the core runtime is correct,
* optimize publication diffs before the new reducer pipeline is stable.

Those are exactly the kinds of choices that make a rewrite sprawl.

---

## 20. Final canonical instruction to the team

If this were the engineering direction memo, it would be:

> We are replacing `niri-state` with a simpler state engine that stores canonical `niri-pypc` models directly, derives secondary indexes lazily, centralizes reconciliation, validates invariants at publication time, and uses Pydantic only at the public immutable boundary. We are not preserving the wrapper architecture, not optimizing for backwards compatibility, and not mirroring `niri-pypc`’s wire-model patterns internally.

That is the cleanest version of the library.

If you want, the next useful artifact is a **full code skeleton** for the new package with all class/function stubs filled in so implementation can start immediately.
